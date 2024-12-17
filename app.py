from flask import abort, Flask, jsonify, request, render_template, Response
from json import dumps
import logging
import requests
import os


app = Flask(__name__)

formatter = logging.Formatter("%(asctime)s %(levelname)s %(funcName)s %(message)s")
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("logger")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

API_URL = os.environ["OPB_API_URL"]
API_KEY = os.environ["OPB_TEST_API_KEY"]
HEADERS = {"X-API-KEY": API_KEY}

def api_request(endpoint, method="POST", data=None, files=None, params=None, timeout=None):
    url = f"{API_URL}/{endpoint}"
    logger.info("Making %s request to /%s", method, endpoint)
    if method == "GET":
        return requests.get(url, headers=HEADERS, params=data, timeout=timeout)
    else:
        return requests.post(url, headers=HEADERS, json=data, files=files, params=params, timeout=timeout)


def api_request_stream(endpoint, data=None):
    url = f"{API_URL}/{endpoint}"
    logger.info("Making streaming request to %s", endpoint)
    return requests.post(url, headers=HEADERS, json=data, stream=True)


@app.route("/bot/<bot>", methods=["GET"])
@app.route("/bot/<bot>/", methods=["GET"])
@app.route("/bot/<bot>/session/<session>", methods=["GET"])
def chatbot(bot, session=None):
    data = {"bot_id": bot}
    logger.info("Fetching bot info for ID %s", bot)
    try:
        with api_request("view_bot", data=data, method="GET") as r:
            r.raise_for_status()
            result = r.json()
    except Exception:
        logger.exception("Fetch bot info failed.")
        return jsonify({"error": "Failed to load agent."}), 400
    logger.debug("Fetched bot info: %s", result)
    if result["data"] is None:
        logger.error("Fetch bot info received an unexpected response.")
        abort(404)
    engine, model = None, None
    if "chat_model" in result["data"]:
        engine = result["data"]["chat_model"]["engine"]
        model = result["data"]["chat_model"]["model"]
    search_tools = []
    if "search_tools" in result["data"]:
        search_tools = result["data"]["search_tools"]
    vdb_tools = []
    if "vdb_tools" in result["data"]:
        vdb_tools = result["data"]["vdb_tools"]
    return render_template("index.html", engine=engine, model=model, search_tools=search_tools, vdb_tools=vdb_tools)


@app.route("/chat", methods=["GET", "POST"])
def chat():
    if request.method == "POST":
        # Get the message and files from the request
        files = request.files.getlist("files")
        session_id = request.form.get("sessionId")

        if files:
            logger.info("Uploading files...")
            # Prepare files for upload
            files_to_upload = [
                ("files", (file.filename, file.stream, file.content_type))
                for file in files
            ]
            # Call the FastAPI file upload endpoint
            try:
                with api_request(
                    "upload_files",
                    files=files_to_upload,
                    params={"session_id": session_id},
                ) as r:
                    r.raise_for_status()
                    result = r.json()
            except Exception:
                logger.exception("Upload files failed.")
                return jsonify({"error": "Failed to upload files"}), 400
            logger.info("Files finished uploading. Result: %s", result)
            return jsonify(result), 200
        logger.warning("No files were provided.")
        return jsonify({"error": "No files provided"}), 400
    else:
        session_id = request.args.get("sessionId")
        message = request.args.get("message")
        request_data = {
            "session_id": session_id,
            "message": message,
        }

        def generate():
            try:
                with api_request_stream("chat_session_stream", data=request_data) as r:
                    r.raise_for_status()
                    for line in r.iter_lines(decode_unicode=True):
                        if line:
                            yield f"data: {line}\n\n"
            except Exception:
                logger.exception("Streaming error occurred.")
                e_msg = dumps({"type": "error"})
                yield f"data: {e_msg}\n\n"
            finally:
                done = dumps({"type": "done"})
                yield f"data: {done}\n\n"
                return

        logger.info("Streaming chat response for request: %s", request_data)
        return Response(generate(), mimetype="text/event-stream")


@app.route("/bot/<bot>/new_session", methods=["GET"])
def new_session(bot):
    logger.info("Starting new session for bot ID %s", bot)
    try:
        with api_request("initialize_session", data={"bot_id": bot}) as r:
            r.raise_for_status()
            return jsonify(r.json())
    except Exception:
        logger.exception("New session error occurred.")
        return jsonify({"error": "Failed to create session."}), 400


@app.route("/bot/<bot>/info", methods=["GET"])
def bot_info(bot):
    data = {"bot_id": bot}
    logger.info("Bot info endpoint called for ID %s", bot)
    try:
        with api_request("view_bot", data=data, method="GET") as r:
            r.raise_for_status()
            result = r.json()
    except Exception:
        logger.exception("Bot info endpoint fetch failed.")
        return jsonify({"error": "Failed to load agent."}), 400
    if result["data"] is None:
        logger.error("Bot info endpoint got an unexpected response.")
        abort(404)
    logger.debug("Bot endpoint info got response: %s", result)
    return jsonify(result)

@app.route("/sessions", methods=["GET"])
def get_sessions():
    # Get all sessions for this browser from localStorage on client side
    # Then fetch session info from API for each session ID
    try:
        sessions = []
        logger.info("Sessions endpoint called.")
        for session_id in request.args.getlist("ids[]"):
            logger.info("Fetching session info for session ID %s", session_id)
            data = {"session_id": session_id}
            with api_request("fetch_session", data=data) as r:
                r.raise_for_status()
                session_data = r.json()
                sessions.append({
                    "id": session_id,
                    "title": session_data.get("title", "Untitled Chat"),
                    "lastModified": session_data.get("last_modified"),
                    "botId": session_data.get("bot_id"),
                })
        logger.info("Sessions endpoint got responses: %s", sessions)
        return jsonify(sessions)
    except Exception:
        logger.exception("Sessions endpoint got an unexpected response.")
        return jsonify({"error": "Failed to fetch sessions."}), 400


@app.route("/get_session_messages/<session_id>", methods=["GET"])
def get_session_messages(session_id):
    logger.info("Session messages endpoint called for session ID %s", session_id)
    try:
        data = {"session_id": session_id}
        with api_request("fetch_session_formatted_history", data=data) as r:
            r.raise_for_status()
            session_data = r.json()
            logger.debug("Session messages endpoint got response: %s", session_data)
            return jsonify(session_data)
    except Exception:
        logger.exception("Session messages endpoint got an unexpected response.")
        return jsonify({"error": "Failed to fetch messages."}), 400


@app.route("/status", methods=["GET"])
def get_status():
    logger.info("Status endpoint called.")
    try:
        with api_request("", method="GET", timeout=5) as r:
            r.raise_for_status()
    except requests.exceptions.Timeout:
        logger.exception("Status endpoint timed out.")
        return {"status": "timeout"}
    except Exception:
        logger.exception("Status endpoint got an unexpected response")
        return jsonify({"status": "not ok"}), 400
    logger.info("Status endpoint got OK response.")
    return jsonify({"status": "ok"})
