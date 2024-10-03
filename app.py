from flask import Flask, jsonify, request, render_template
from json import dumps
import requests
import os


app = Flask(__name__)

API_URL = "http://0.0.0.0:8080"
API_KEY = os.environ["OPB_TEST_API_KEY"]
HEADERS = {"X-API-KEY": API_KEY}
BOT_ID = "b3030cc8-2256-4924-8d85-6cf1c1d246c2"
REQUEST_DATA = {"bot_id": BOT_ID}

def api_request(endpoint, method="POST", data=None, files=None, params=None):
    url = f"{API_URL}/{endpoint}"
    if method == "GET":
        return requests.get(url, headers=HEADERS, params=data)
    else:
        return requests.post(url, headers=HEADERS, json=data, files=files, params=params)


def api_request_stream(endpoint, data=None):
    url = f"{API_URL}/{endpoint}"
    return requests.post(url, headers=HEADERS, json=data, stream=True)


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/test", methods=["GET", "POST"])
def test_chat():
    message = request.form.get("message")
    bot_id = request.form.get("bot_id")
    # create a session
    try:
        data = {"bot_id": bot_id, "message": message}
        with api_request("initialize_session_chat", data=data) as r:
            r.raise_for_status()
            return jsonify(r.json()), 200
    except Exception as e:
        return jsonify({"error": f"Failed to initialize session: {e}"}), 400

@app.route("/chat", methods=["GET", "POST"])
def chat():
    if request.method == "POST":
        # Get the message and files from the request
        message = request.form.get("message")
        files = request.files.getlist("files")

        # create a session
        try:
            with api_request("initialize_session", data=REQUEST_DATA) as r:
                r.raise_for_status()
                session_id = r.json()["session_id"]
        except Exception as e:
            return jsonify({"error": f"Failed to initialize session: {e}"}), 400

        REQUEST_DATA["session_id"] = session_id

        if files:
            # Prepare files for upload
            files_to_upload = [
                ('files', (file.filename, file.stream, file.content_type))
                for file in files
            ]
            # Call the FastAPI file upload endpoint
            try:
                with api_request(
                    "upload_files",
                    files=files_to_upload,
                    params={"session_id":session_id},
                ) as r:
                    r.raise_for_status()
            except Exception as e:
                return jsonify({"error": f"Failed to upload files: {e}"}), 400

        if message:
            REQUEST_DATA["message"] = message

        return jsonify({"message": "Success"}), 200
    else:
        # Call the FastAPI chat endpoint and stream the response
        def generate():
            try:
                with api_request_stream("chat_session_stream", data=REQUEST_DATA) as r:
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

        return app.response_class(generate(), mimetype="text/event-stream")
