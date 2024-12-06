from flask import abort, Flask, jsonify, request, render_template, Response
from json import dumps
import requests
import os


app = Flask(__name__)

API_URL = os.environ["OPB_API_URL"]
API_KEY = os.environ["OPB_TEST_API_KEY"]
HEADERS = {"X-API-KEY": API_KEY}

def api_request(endpoint, method="POST", data=None, files=None, params=None):
    url = f"{API_URL}/{endpoint}"
    if method == "GET":
        return requests.get(url, headers=HEADERS, params=data)
    else:
        return requests.post(url, headers=HEADERS, json=data, files=files, params=params)


def api_request_stream(endpoint, data=None):
    url = f"{API_URL}/{endpoint}"
    return requests.post(url, headers=HEADERS, json=data, stream=True)


@app.route("/bot/<bot>", methods=["GET"])
@app.route("/bot/<bot>/", methods=["GET"])
@app.route("/bot/<bot>/session/<session>", methods=["GET"])
def chatbot(bot, session=None):
    data = {"bot_id": bot}
    try:
        with api_request("view_bot", data=data, method="GET") as r:
            r.raise_for_status()
            result = r.json()
    except Exception as e:
        return jsonify({"error": f"Failed to load agent: {e}"}), 400
    if result["data"] is None:
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
            except Exception as e:
                return jsonify({"error": f"Failed to upload files: {e}"}), 400
            return jsonify(result), 200
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
            except Exception as e:
                e_msg = dumps({"type": "error","message":str(e)})
                yield f"data: {e_msg}\n\n"
            finally:
                done = dumps({"type": "done"})
                yield f"data: {done}\n\n"
                return

        return Response(generate(), mimetype="text/event-stream")


@app.route("/bot/<bot>/new_session", methods=["GET"])
def new_session(bot):
    try:
        with api_request("initialize_session", data={"bot_id": bot}) as r:
            r.raise_for_status()
            return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": f"Failed to create session: {e}"}), 400


@app.route("/bot/<bot>/info", methods=["GET"])
def bot_info(bot):
    data = {"bot_id": bot}
    try:
        with api_request("view_bot", data=data, method="GET") as r:
            r.raise_for_status()
            result = r.json()
    except Exception as e:
        return jsonify({"error": f"Failed to load agent: {e}"}), 400
    if result["data"] is None:
        abort(404)
    return jsonify(result)

@app.route("/sessions", methods=["GET"])
def get_sessions():
    # Get all sessions for this browser from localStorage on client side
    # Then fetch session info from API for each session ID
    try:
        sessions = []
        for session_id in request.args.getlist("ids[]"):
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
        return jsonify(sessions)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch sessions: {e}"}), 400


@app.route("/get_session_messages/<session_id>", methods=["GET"])
def get_session_messages(session_id):
    try:
        data = {"session_id": session_id}
        with api_request("fetch_session_formatted_history", data=data) as r:
            r.raise_for_status()
            session_data = r.json()
            return jsonify(session_data)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch messages: {e}"}), 400