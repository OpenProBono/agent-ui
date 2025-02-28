import datetime
import logging
import os
import time
from json import dumps, loads

import requests
from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    render_template,
    request,
)

from app_helper import (
    JURISDICTIONS,
    format_summary,
    generate_source_context,
    organize_sources,
)

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

formatter = logging.Formatter("%(asctime)s %(levelname)s %(funcName)s %(message)s")
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("logger")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

API_URL = "http://0.0.0.0:8080"
API_KEY = os.environ["OPB_TEST_API_KEY"]
HEADERS = {"X-API-KEY": API_KEY}


def api_request(endpoint, method="POST", data=None, files=None, params=None, timeout=None, stream=None):
    url = f"{API_URL}/{endpoint}"
    logger.info("Making %s request to /%s", method, endpoint)
    if method == "GET":
        return requests.get(url, headers=HEADERS, params=data, timeout=timeout, stream=stream)
    return requests.post(url, headers=HEADERS, json=data, files=files, params=params, timeout=timeout, stream=stream)


@app.route("/")
@app.route("/dashboard")
def index():
    # Example data
    agents = [
        {"id": 1, "name": "default_bot"},
        {"id": 2, "name": "default_anthropic"},
        {"id": 3, "name": "manual_sources_case_search"},
    ]
    metrics = {
        "agents_created": len(agents),
        "messages_with_agents": 150,
        "searches_completed": 45,
        "file_storage_used": "2 GB",
    }
    return render_template("index.html", agents=agents, metrics=metrics)


@app.route("/signup")
def signup():
    # firebase_config = {
    #     "apiKey": os.environ.get("FIREBASE_API_KEY"),
    #     "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN"),
    #     "projectId": os.environ.get("FIREBASE_PROJECT_ID")
    # }
    # return render_template("index.html", firebase_config=firebase_config)
    return render_template("signup.html")

@app.route("/agents")
def agents():
    # Example data
    agents = [
        {"id": 1, "name": "default_bot", "created_on": datetime.date.today(), "tools": 2, "resources": 10, "dynamic": True},
        {"id": 2, "name": "default_anthropic", "created_on": datetime.date.today(), "tools": 1, "resources": 4, "dynamic": False},
        {"id": 3, "name": "manual_sources_case_search", "created_on": datetime.date.today(), "tools": 4, "resources": 150, "dynamic": True},
    ]
    return render_template("agents.html", agents=agents)


@app.route("/resources")
def resources():
    # Example data
    collections = [
        {"name": "search_collection_vj1", "created_on": datetime.date.today(), "resource_count": 10000},
        {"name": "courtlistener", "created_on": datetime.date.today(), "resource_count": 1000000},
        {"name": "search_collection_gemini", "created_on": datetime.date.today(), "resource_count": 10000},
    ]
    resources = [
        {"name": "helpguide.pdf", "added_on": datetime.date.today(), "collection_count": 2},
        {"name": "www.google.com", "added_on": datetime.date.today(), "collection_count": 1},
    ]
    return render_template("resources.html", collections=collections, resources=resources)


@app.route("/agent/<agent>", methods=["GET"])
@app.route("/agent/<agent>/", methods=["GET"])
@app.route("/agent/<agent>/session/<session>", methods=["GET"])
def chatbot(agent, session=None):
    data = {"bot_id": agent}
    logger.info("Fetching agent info for ID %s", agent)
    try:
        with api_request("view_bot", data=data, method="GET") as r:
            r.raise_for_status()
            result = r.json()
    except Exception:
        logger.exception("Fetch agent info failed.")
        return jsonify({"error": "Failed to load agent."}), 400
    logger.debug("Fetched agent info: %s", result)
    if result["data"] is None:
        logger.error("Fetch agent info received an unexpected response.")
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
    # name is the agent name with capitalized first letters
    # and underscores replaced with spaces
    name = " ".join(word.capitalize() for word in agent.split("_"))
    return render_template(
        "chatbot.html",
        engine=engine,
        model=model,
        search_tools=search_tools,
        vdb_tools=vdb_tools,
        name=name,
    )

@app.route("/users", methods=["GET"])
@app.route("/users/", methods=["GET"])
def users():
    example_data = [{
        "id": 1,
        "name": "Nick",
        "email": "nick@openprobono.com",
        "role": "Admin",
    },
    {
        "id": 2,
        "name": "Arman",
        "email": "arman@openprobono.com",
        "role": "User",
    }]
    return render_template("users.html", users=example_data)


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
                with api_request("chat_session_stream", data=request_data, stream=True) as r:
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


@app.route("/agent/<agent>/new_session", methods=["GET"])
def new_session(agent):
    logger.info("Starting new session for agent ID %s", agent)
    try:
        with api_request("initialize_session", data={"bot_id": agent}) as r:
            r.raise_for_status()
            return jsonify(r.json())
    except Exception:
        logger.exception("New session error occurred.")
        return jsonify({"error": "Failed to create session."}), 400


@app.route("/agent/<agent>/info", methods=["GET"])
def agent_info(agent):
    data = {"bot_id": agent}
    logger.info("Agent info endpoint called for ID %s", agent)
    try:
        with api_request("view_bot", data=data, method="GET") as r:
            r.raise_for_status()
            result = r.json()
    except Exception:
        logger.exception("Agent info endpoint fetch failed.")
        return jsonify({"error": "Failed to load agent."}), 400
    if result["data"] is None:
        logger.error("Agent info endpoint got an unexpected response.")
        abort(404)
    logger.debug("Agent endpoint info got response: %s", result)
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
                    "lastModified": session_data.get("timestamp"),
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


@app.route("/feedback", methods=["POST"])
def feedback():
    logger.info("Feedback endpoint called.")
    feedback_data = loads(request.form.get("data"))
    feedback_index = request.form.get("index")
    session_id = request.form.get("sessionId")
    data = {
        "feedback_text": feedback_data["comment"],
        "session_id": session_id,
        "feedback_type": feedback_data["type"],
        "message_index": feedback_index,
        "categories": feedback_data["categories"] if feedback_data["type"] == "dislike" else [],
    }
    try:
        with api_request("session_feedback", data=data) as r:
            r.raise_for_status()
            result = r.json()
    except Exception:
        logger.exception("Feedback failed.")
        return jsonify({"status": "not ok"}), 400
    if result["message"] == "Success":
        logger.info("Feedback submitted.")
        status = "ok"
    else:
        logger.info("Feedback failed to submit.")
        status = "not ok"
    return jsonify({"status": status})


@app.route("/search/<collection>", methods=["GET"])
def search(collection):
    start = time.time()
    if not collection:
        abort(404)
    semantic = request.args.get("semantic")
    if not semantic:
        return render_template("search.html", collection=collection, jurisdictions=JURISDICTIONS)
    keyword = request.args.get("keyword")
    jurisdictions = request.args.getlist("jurisdictions")
    after_date = request.args.get("after_date")
    before_date = request.args.get("before_date")
    data = {
        "collection": collection,
        "query": semantic,
        "k": 100,
    }
    if keyword:
        data["keyword_query"] = keyword
    if jurisdictions and len(jurisdictions) != len(JURISDICTIONS):
        data["jurisdictions"] = jurisdictions
    if after_date:
        data["after_date"] = after_date
    if before_date:
        data["before_date"] = before_date
    try:
        with api_request("search_collection", data=data) as r:
            r.raise_for_status()
            result = r.json()
    except Exception:
        logger.exception("Search endpoint fetch failed.")
        return jsonify({"error": "Failed to search collection."}), 400
    if result["results"] is None:
        logger.error("Search endpoint got an unexpected response.")
        return jsonify({"error": "Failed to search collection."}), 400
    results = result["results"]
    organized = organize_sources(results)
    sources = [
        generate_source_context(s["source"], i, s["entities"], keyword=keyword)
        for i, s in enumerate(organized)
    ]
    end = time.time()
    elapsed = str(round(end - start, 5))
    return render_template(
        "search.html",
        collection=collection,
        results=sources,
        results_count=len(results),
        form_data=data,
        elapsed=elapsed,
        jurisdictions=JURISDICTIONS,
    )

@app.route("/manage/<collection>", methods=["GET"])
def manage(collection):
    start = time.time()
    if not collection:
        abort(404)
    source = request.args.get("source")
    keyword = request.args.get("keyword")
    jurisdictions = request.args.getlist("jurisdictions")
    after_date = request.args.get("after_date")
    before_date = request.args.get("before_date")
    page = request.args.get("page", 1, int)
    per_page = request.args.get("per_page", 50, int)
    params = {"page": page, "per_page": per_page}
    data = {"collection": collection}
    if keyword:
        data["keyword_query"] = keyword
    if jurisdictions and len(jurisdictions) != len(JURISDICTIONS):
        data["jurisdictions"] = jurisdictions
    if after_date:
        data["after_date"] = after_date
    if before_date:
        data["before_date"] = before_date
    if source:
        data["source"] = source
    try:
        with api_request("browse_collection", data=data, params=params) as r:
            r.raise_for_status()
            result = r.json()
    except Exception:
        logger.exception("Manage endpoint fetch failed.")
        return jsonify({"error": "Failed to manage collection."}), 400
    if result["results"] is None:
        logger.error("Manage endpoint got an unexpected response.")
        return jsonify({"error": "Failed to manage collection."}), 400
    results = result["results"]
    organized = organize_sources(results)
    sources = [
        generate_source_context(s["source"], i, s["entities"], keyword=keyword)
        for i, s in enumerate(organized)
    ]
    end = time.time()
    elapsed = str(round(end - start, 5))
    return render_template(
        "manage_collection.html",
        collection=collection,
        results=sources,
        results_count=len(results),
        form_data=data,
        elapsed=elapsed,
        jurisdictions=JURISDICTIONS,
        page=page,
        per_page=per_page,
        has_next=result["has_next"],
    )

@app.route("/resource_count/<collection_name>")
def get_resource_count(collection_name) -> int:
    try:
        with api_request(f"resource_count/{collection_name}", method="GET", timeout=45) as r:
            r.raise_for_status()
            result = r.json()
    except Exception:
        logger.exception("Resource count endpoint got an unexpected response.")
        return {"message": "Failure: exception in request or bad response code"}
    if "resource_count" in result:
        return {"message": "Success", "resource_count": result["resource_count"]}
    return {"message": "Failure: no resource count found"}


@app.route("/summary/<resource_id>")
def fetch_summary(resource_id):
    params = {"resource_id": resource_id}
    try:
        with api_request("summary", method="GET", params=params, timeout=30) as r:
            r.raise_for_status()
            result = r.json()
    except Exception:
        logger.exception("Summary endpoint got an unexpected response.")
        return {"message": "Failure: exception in request or bad response code"}
    if "result" not in result:
        return {"message": "Failure: no summary found"}
    summary = result["result"]
    return {"message": "Success", "summary": format_summary(summary)}


@app.route("/create-agent", methods=["GET", "POST"])
def create_agent():
    if request.method == "GET":
        return render_template("create_agent.html")
    # Retrieve core fields
    system_prompt = request.form.get("system_prompt", None)
    message_prompt = request.form.get("message_prompt", None)
    search_names = request.form.getlist("search_names[]")
    search_methods = request.form.getlist("search_methods[]")
    search_prefixes = request.form.getlist("search_prefixes[]")
    search_prompts = request.form.getlist("search_prompts[]")
    vdb_names = request.form.getlist("vdb_names[]")
    vdb_collections = request.form.getlist("vdb_collections[]")
    vdb_ks = request.form.getlist("vdb_ks[]")
    vdb_prompts = request.form.getlist("vdb_prompts[]")

    # Build search tools list
    search_tools = [
        {
            "name": search_names[i],
            "method": search_methods[i],
            "prefix": search_prefixes[i],
            "prompt": search_prompts[i],
        }
        for i in range(len(search_names))
    ]

    # Build VDB tools list
    vdb_tools = [
        {
            "name": vdb_names[i],
            "collection_name": vdb_collections[i],
            "k": int(vdb_ks[i]),
            "prompt": vdb_prompts[i],
        }
        for i in range(len(vdb_names))
    ]

    # Chat model configuration
    chat_model = {
        "engine": request.form.get("engine", "openai"),
        "model": request.form.get("model", "gpt-4o"),
        "temperature": float(request.form.get("temperature", 0)),
        "seed": int(request.form.get("seed", 0)),
    }

    bot_data = {
        "search_tools": search_tools,
        "vdb_tools": vdb_tools,
        "chat_model": chat_model,
    }
    if system_prompt:
        bot_data["system_prompt"] = system_prompt
    if message_prompt:
        bot_data["message_prompt"] = message_prompt


    try:
        with api_request("create_bot", data=bot_data) as r:
            r.raise_for_status()
            result = r.json()
    except Exception:
        logger.exception("Create agent failed.")
        return jsonify({"error": "Failed to create agent."}), 400
    logger.debug("Created agent: %s", result)
    if result["message"] != "Success":
        logger.error("Create agent received an unexpected response.")
        flash("Failed to create agent.", "error")
        return render_template("create_agent.html")
    if "bot_id" in result:
        flash(f"Agent created successfully! Agent ID: {result['bot_id']}", "success")
        flash(f"You can now chat with your agent at /agent/{result['bot_id']}", "info")
        return render_template("create_agent.html")
    flash("Failed to create agent.", "error")
    return render_template("create_agent.html")


@app.route("/clone/<agent>", methods=["GET"])
def clone_agent(agent):
    data = {"bot_id": agent}
    logger.info("Fetching agent info for ID %s", agent)
    try:
        with api_request("view_bot", data=data, method="GET") as r:
            r.raise_for_status()
            result = r.json()
    except Exception:
        logger.exception("Fetch agent info failed.")
        return jsonify({"error": "Failed to load agent."}), 400
    logger.debug("Fetched agent info: %s", result)
    if result["data"] is None:
        logger.error("Fetch agent info received an unexpected response.")
        abort(404)
    engine, model, temperature, seed = None, None, None, None
    if "chat_model" in result["data"]:
        engine = result["data"]["chat_model"]["engine"]
        model = result["data"]["chat_model"]["model"]
        temperature = result["data"]["chat_model"]["temperature"]
        seed = result["data"]["chat_model"]["seed"]
    search_tools = []
    if "search_tools" in result["data"]:
        search_tools = result["data"]["search_tools"]
    vdb_tools = []
    if "vdb_tools" in result["data"]:
        vdb_tools = result["data"]["vdb_tools"]
    system_prompt = None
    if "system_prompt" in result["data"]:
        system_prompt = result["data"]["system_prompt"]
    message_prompt = None
    if "message_prompt" in result["data"]:
        message_prompt = result["data"]["message_prompt"]
    name = " ".join(word.capitalize() for word in agent.split("_"))
    agent = {
        "name": name,
        "system_prompt": system_prompt,
        "message_prompt": message_prompt,
        "search_tools": search_tools,
        "vdb_tools": vdb_tools,
        "engine": engine,
        "model": model,
        "temperature": temperature,
        "seed": seed,
    }
    return render_template("create_agent.html", clone=True, agent=agent)
