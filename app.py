import datetime
import os
import time
from json import dumps, loads
from typing import List

import requests
from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
)

from app_helper import (
    JURISDICTIONS,
    api_request,
    format_summary,
    generate_source_context,
    logger,
    organize_sources,
    api_url,
)

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]


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
    id_token = session.get("id_token")
    user = {
        "email": session.get("email"),
        "firebase_uid": session.get("firebase_uid")
    }
    if(not id_token):
        return redirect("/signup")
    return render_template("index.html", agents=agents, metrics=metrics, user=user)


@app.route("/signup")
def signup():
    logger.info("Signup endpoint called.")
    return render_template("signup.html")


@app.route("/login", methods=["POST"])
def login():
    logger.info("Login endpoint called.")
    session["email"] = request.json.get("email")
    session["firebase_uid"] = request.json.get("firebase_uid")
    session["id_token"] = request.json.get("idToken")
    return redirect("/")


@app.route("/logout")
def logout():
    logger.info("Logout endpoint called.")
    session.clear()
    return redirect("/")


@app.route("/agents")
def agents():
    logger.info("Agents endpoint called.")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    # Initialize agents list
    agents = []
    
    # If user is authenticated, fetch real agent data
    if id_token:
        try:
            with api_request("view_bots", method="POST", data={"user": user}, id_token=id_token) as r:
                if r.status_code == 200:
                    response_data = r.json()
                    if response_data.get("message") == "Success" and "data" in response_data:
                        # Transform the API response to match the expected format for the template
                        for bot_id, bot in response_data["data"].items():
                            # Count total tools (search_tools + vdb_tools)
                            search_tools = bot.get("search_tools", [])
                            vdb_tools = bot.get("vdb_tools", [])
                            total_tools = len(search_tools) + len(vdb_tools)
                            
                            # Count resources (assuming vdb_tools represent resources)
                            resources = len(vdb_tools)
                            
                            # Determine if bot is dynamic (has search tools)
                            is_dynamic = len(search_tools) > 0
                            
                            agent = {
                                "id": bot_id,
                                "name": bot.get("name", "Untitled Bot"),
                                "created_on": datetime.datetime.fromisoformat(bot.get("created_at", datetime.datetime.now().isoformat())).date() if bot.get("created_at") else datetime.date.today(),
                                "tools": total_tools,
                                "resources": resources,
                                "dynamic": is_dynamic
                            }
                            agents.append(agent)
                else:
                    logger.error(f"Failed to fetch agents: {r.status_code} - {r.text}")
        except Exception as e:
            logger.error(f"Error fetching agents: {str(e)}")
    
    # If no agents were fetched (either due to error or user not authenticated),
    # provide example data for display purposes
    if not agents:
        logger.warning("Using example agent data as no real data was fetched.")
        agents = [
            {"id": 1, "name": "default_bot", "created_on": datetime.date.today(), "tools": 2, "resources": 10, "dynamic": True},
            {"id": 2, "name": "default_anthropic", "created_on": datetime.date.today(), "tools": 1, "resources": 4, "dynamic": False},
            {"id": 3, "name": "manual_sources_case_search", "created_on": datetime.date.today(), "tools": 4, "resources": 150, "dynamic": True},
        ]
    
    return render_template("agents.html", agents=agents, user=user)


@app.route("/resources")
def resources():
    logger.info("Resources endpoint called.")
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
    user = {
        "email": session.get("email"),
        "firebase_uid": session.get("firebase_uid")
    }
    return render_template("resources.html", collections=collections, resources=resources, user=user)


@app.route("/agent/<agent>", methods=["GET"])
@app.route("/agent/<agent>/", methods=["GET"])
@app.route("/agent/<agent>/session/<session_id>", methods=["GET"])
def chatbot(agent, session_id=None):
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    data = {"bot_id": agent, "user": user}
    logger.info("Fetching agent info for ID %s", agent)
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")

    try:
        with api_request("view_bot", method="POST", id_token=id_token, params=data) as r:
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
    # Use the actual name from the API response if available, otherwise derive from agent ID
    name = result["data"].get("name") if result["data"].get("name") else " ".join(word.capitalize() for word in agent.split("_"))
    return render_template(
        "chatbot.html",
        engine=engine,
        model=model,
        search_tools=search_tools,
        vdb_tools=vdb_tools,
        name=name,
        user=user,
    )

@app.route("/users", methods=["GET"])
@app.route("/users/", methods=["GET"])
def users():
    logger.info("Users endpoint called.")
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
    user = {
        "email": session.get("email"),
        "firebase_uid": session.get("firebase_uid")
    }
    return render_template("users.html", users=example_data, user=user)


@app.route("/chat", methods=["GET", "POST"])
def chat():
    logger.info("Chat endpoint called.")
    id_token = session.get("id_token")
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    if not id_token:
        return redirect("/signup")

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
                    id_token=id_token,
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
            "user": user
        }

        def generate():
            try:
                with api_request("chat_session_stream", id_token=id_token, data=request_data, stream=True) as r:
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
    id_token = session.get("id_token")
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    if not id_token:
        return redirect("/signup")
    try:
        with api_request("initialize_session", id_token=id_token, data={"bot_id": agent, "user": user}) as r:
            r.raise_for_status()
            return jsonify(r.json())
    except Exception:
        logger.exception("New session error occurred.")
        return jsonify({"error": "Failed to create session."}), 400


@app.route("/agent/<agent>/info", methods=["GET"])
def agent_info(agent):
    data = {"bot_id": agent}
    logger.info("Agent info endpoint called for ID %s", agent)
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")

    try:
        with api_request("view_bot", id_token=id_token, params=data, method="POST") as r:
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
        id_token = session.get("id_token")
        if not id_token:
            return redirect("/signup")

        for session_id in request.args.getlist("ids[]"):
            logger.info("Fetching session info for session ID %s", session_id)
            user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
            data = {"session_id": session_id, "user": user}
            with api_request("fetch_session", id_token=id_token, data=data) as r:
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


@app.route("/sessions-page", methods=["GET"])
def sessions_page():
    """Page to view all the user's previous chat sessions with filtering capability."""
    logger.info("Sessions page endpoint called.")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")
    
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    
    # Get all available bots for filtering options
    bots = {}
    try:
        with api_request("view_bots", method="POST", data={"user": user}, id_token=id_token) as r:
            if r.status_code == 200:
                response_data = r.json()
                if response_data.get("message") == "Success" and "data" in response_data:
                    bots = response_data["data"]
    except Exception:
        logger.exception("Failed to fetch bots for sessions page.")
    
    # Fetch all sessions for this user
    sessions = []
    try:
        with api_request("fetch_sessions", method="POST", data={"firebase_uid": user["firebase_uid"], "user": user}, id_token=id_token) as r:
            if r.status_code == 200:
                response_data = r.json()
                if response_data.get("message") == "Success" and "sessions" in response_data:
                    sessions = response_data["sessions"]
                    logger.info(f"Fetched {len(sessions)} sessions for user")
    except Exception:
        logger.exception("Failed to fetch sessions for user")
    
    return render_template("sessions.html", user=user, bots=bots, sessions=sessions)


@app.route("/get_session_messages/<session_id>", methods=["GET"])
def get_session_messages(session_id):
    logger.info("Session messages endpoint called for session ID %s", session_id)
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")

    try:
        user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
        data = {"session_id": session_id, "user": user}
        with api_request("fetch_session_formatted_history", id_token=id_token, data=data) as r:
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
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")
    try:
        with api_request("", method="GET", id_token=id_token, timeout=5) as r:
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
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")

    feedback_data = loads(request.form.get("data"))
    feedback_index = request.form.get("index")
    session_id = request.form.get("sessionId")
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    data = {
        "feedback_text": feedback_data["comment"],
        "session_id": session_id,
        "feedback_type": feedback_data["type"],
        "message_index": feedback_index,
        "categories": feedback_data["categories"] if feedback_data["type"] == "dislike" else [],
        "user": user
    }
    try:
        with api_request("session_feedback", id_token=id_token, data=data) as r:
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
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")
    if not collection:
        abort(404)
    semantic = request.args.get("semantic")
    if not semantic:
        email = session.get("email")
        user = {
            "email": email,
            "firebase_uid": session.get("firebase_uid")
        }
        return render_template("search.html", collection=collection, jurisdictions=JURISDICTIONS, user=user)
    keyword = request.args.get("keyword")
    jurisdictions = request.args.getlist("jurisdictions")
    after_date = request.args.get("after_date")
    before_date = request.args.get("before_date")
    data = {
        "collection": collection,
        "query": semantic,
        "k": 100,
        "user": user
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
        with api_request("search_collection", id_token=id_token, data=data) as r:
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
    email = session.get("email")
    user = {
        "email": email,
        "firebase_uid": session.get("firebase_uid")
    }
    return render_template(
        "search.html",
        collection=collection,
        results=sources,
        results_count=len(results),
        form_data=data,
        elapsed=elapsed,
        jurisdictions=JURISDICTIONS,
        user=user,
    )

@app.route("/manage/<collection>", methods=["GET"])
def manage(collection):
    start = time.time()
    if not collection:
        abort(404)
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")
    source = request.args.get("source")
    keyword = request.args.get("keyword")
    jurisdictions = request.args.getlist("jurisdictions")
    after_date = request.args.get("after_date")
    before_date = request.args.get("before_date")
    page = request.args.get("page", 1, int)
    per_page = request.args.get("per_page", 50, int)
    params = {"page": page, "per_page": per_page}
    user = {
        "email": session.get("email"),
        "firebase_uid": session.get("firebase_uid")
    }
    data = {"collection": collection, "user": user}
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
        with api_request("browse_collection", id_token=id_token, data=data, params=params) as r:
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
        user=user,
    )

@app.route("/resource_count/<collection_name>")
def get_resource_count(collection_name) -> int:
    logger.info("Getting resource count for collection %s.", collection_name)
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")
    try:
        with api_request(f"resource_count/{collection_name}", method="GET", id_token=id_token, timeout=45) as r:
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
    logger.info("Fetching summary for %s.", resource_id)
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")
    params = {"resource_id": resource_id}
    try:
        with api_request("summary", method="GET", id_token=id_token, params=params, timeout=30) as r:
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
    logger.info("Create agent endpoint called.")
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    if request.method == "GET":
        return render_template("create_agent.html", user=user)
    # Retrieve core fields
    bot_name = request.form.get("bot_name", None)
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
        "name": bot_name,
        "search_tools": search_tools,
        "vdb_tools": vdb_tools,
        "chat_model": chat_model,
        "user": user,
    }
    if system_prompt:
        bot_data["system_prompt"] = system_prompt
    if message_prompt:
        bot_data["message_prompt"] = message_prompt


    try:
        with api_request("create_bot", id_token=id_token, data=bot_data) as r:
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
    logger.info("Cloning agent: %s", agent)
    data = {"bot_id": agent}
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")

    logger.info("Fetching agent info for ID %s", agent)
    try:
        with api_request("view_bot", method="POST", id_token=id_token, params=data) as r:
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
    # Use the actual name from the API response if available, otherwise derive from agent ID
    name = result["data"].get("name") if result["data"].get("name") else " ".join(word.capitalize() for word in agent.split("_"))
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
    email = session.get("email")
    user = {
        "email": email,
        "firebase_uid": session.get("firebase_uid")
    }
    return render_template("create_agent.html", clone=True, agent=agent, user=user)


@app.route("/delete-agent/<agent_id>", methods=["GET"])
def delete_agent(agent_id):
    logger.info("Delete agent endpoint called for agent ID: %s", agent_id)
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    if not id_token:
        logger.warning("User not authenticated, redirecting to signup")
        return redirect("/signup")
    
    try:
        # Call the delete_bot/{bot_id} endpoint
        endpoint = f"delete_bot/{agent_id}"
        logger.info("Calling API endpoint: %s", endpoint)
        
        with api_request(endpoint, method="DELETE", id_token=id_token) as r:
            if r.status_code == 200:
                response_data = r.json()
                if("message" in response_data and response_data["message"] == "Success"):
                    logger.info("Successfully deleted agent with ID: %s. Response: %s", agent_id, response_data)
                    flash("Agent successfully deleted", "success")
                else:
                    error_msg = f"Failed to delete agent: {response_data["message"]}"
                    logger.info(error_msg)
                    flash(error_msg, "error")
            else:
                error_msg = f"Failed to delete agent: {r.status_code}"
                try:
                    error_data = r.json()
                    if "message" in error_data:
                        error_msg = error_data["message"]
                except Exception:
                    pass
                logger.error("Failed to delete agent: %s - %s", r.status_code, r.text)
                flash(error_msg, "error")
    except Exception as e:
        logger.exception("Error deleting agent: %s", str(e))
        flash(f"Error deleting agent: {str(e)}", "error")
    
    # Redirect back to the agents page
    return redirect("/agents")


@app.route("/export_sessions", methods=["POST"])
def export_sessions():
    """Export multiple sessions with their full data including messages."""
    logger.info("Export sessions endpoint called.")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    if not id_token:
        return jsonify({"error": "Authentication required"}), 401
    
    # Get user info
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    
    # Get session IDs from request
    try:
        request_data = request.get_json()
        if not request_data or not isinstance(request_data, dict) or "session_ids" not in request_data:
            return jsonify({"error": "Missing session_ids parameter"}), 400
        
        session_ids = request_data["session_ids"]
        if not isinstance(session_ids, list) or not session_ids:
            return jsonify({"error": "session_ids must be a non-empty list"}), 400
        
        logger.info(f"Exporting {len(session_ids)} sessions")
        
        # Get all available bots to retrieve bot names
        bots = {}
        try:
            with api_request("view_bots", method="POST", data={"user": user}, id_token=id_token) as r:
                if r.status_code == 200:
                    response_data = r.json()
                    if response_data.get("message") == "Success" and "data" in response_data:
                        bots = response_data["data"]
        except Exception:
            logger.exception("Failed to fetch bots for export sessions.")
        
        # Fetch data for each session
        exported_sessions = []
        for session_id in session_ids:
            try:
                # Get session metadata
                session_metadata = {}
                with api_request("fetch_session", id_token=id_token, data={"session_id": session_id, "user": user}) as r:
                    if r.status_code == 200:
                        session_metadata = r.json()
                    else:
                        logger.warning(f"Failed to fetch session {session_id}: {r.status_code}")
                        continue
                
                # Get session messages using internal request to our own endpoint
                messages_url = f"{request.host_url.rstrip('/')}/get_session_messages/{session_id}"
                headers = {"Cookie": f"session={request.cookies.get('session', '')}"}
                
                try:
                    messages_response = requests.get(messages_url, headers=headers, timeout=10)
                    if messages_response.status_code == 200:
                        messages_data = messages_response.json()
                        # Add messages to session data
                        session_metadata["messages"] = messages_data.get("history", [])
                    else:
                        logger.warning(f"Failed to fetch messages for session {session_id}: {messages_response.status_code}")
                        session_metadata["messages"] = []
                except Exception as msg_err:
                    logger.exception(f"Error fetching messages for session {session_id}: {str(msg_err)}")
                    session_metadata["messages"] = []
                
                # Get bot name if available
                bot_id = session_metadata.get("bot_id", "")
                bot_name = "Unknown Agent"
                if bot_id and bot_id in bots:
                    bot_name = bots[bot_id].get("name", "Unknown Agent")
                
                # Add to exported sessions
                exported_sessions.append({
                    "session_id": session_id,
                    "bot_id": bot_id,
                    "bot_name": bot_name,
                    "title": session_metadata.get("title", "Untitled Chat"),
                    "timestamp": session_metadata.get("timestamp", ""),
                    "messages": session_metadata.get("messages", [])
                })
                
            except Exception as e:
                logger.exception(f"Error exporting session {session_id}: {str(e)}")
                # Continue with other sessions even if one fails
        
        if not exported_sessions:
            return jsonify({"error": "Failed to export any sessions"}), 500
        
        return jsonify({
            "message": "Success",
            "count": len(exported_sessions),
            "sessions": exported_sessions
        })
        
    except Exception as e:
        logger.exception(f"Export sessions endpoint error: {str(e)}")
        return jsonify({"error": "Failed to export sessions"}), 500

@app.route("/eval-datasets", methods=["GET"])
def eval_datasets():
    """Page to view all evaluation datasets."""
    logger.info("Eval datasets endpoint called.")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")
    
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    
    # Fetch all evaluation datasets for this user
    datasets = []
    try:
        with api_request("get_user_datasets", method="GET", id_token=id_token) as r:
            if r.status_code == 200:
                response_data = r.json()
                if response_data.get("message") == "Success" and "datasets" in response_data:
                    datasets = response_data["datasets"]
                    logger.info(f"Fetched {len(datasets)} evaluation datasets for user")
    except Exception:
        logger.exception("Failed to fetch evaluation datasets for user")
    
    return render_template("eval_datasets.html", user=user, datasets=datasets)


@app.route("/create-eval-dataset", methods=["GET", "POST"])
def create_eval_dataset():
    """Page to create a new evaluation dataset."""
    logger.info("Create eval dataset endpoint called.")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")
    
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    
    if request.method == "GET":
        # Get all available bots for selection
        bots = {}
        try:
            with api_request("view_bots", method="POST", data={"user": user}, id_token=id_token) as r:
                if r.status_code == 200:
                    response_data = r.json()
                    if response_data.get("message") == "Success" and "data" in response_data:
                        bots = response_data["data"]
                        logger.info(f"Fetched {len(bots)} bots for eval dataset creation")
        except Exception:
            logger.exception("Failed to fetch bots for eval dataset creation")
        
        return render_template("create_eval_dataset.html", user=user, bots=bots)
    
    # Handle POST request to create a new dataset
    try:
        # Get form data
        name = request.form.get("name")
        description = request.form.get("description", "")
        inputs_text = request.form.get("inputs", "")
        bot_ids = request.form.getlist("bot_ids")
        
        # Process inputs (split by newlines and remove empty lines)
        inputs = [line.strip() for line in inputs_text.split("\n") if line.strip()]
        
        # Validate required fields
        if not name or not inputs or not bot_ids:
            flash("Please provide a name, at least one input, and select at least one bot.", "error")
            return redirect("/create-eval-dataset")
        
        # Create dataset object
        dataset_data = {
            "name": name,
            "description": description,
            "inputs": inputs,
            "bot_ids": bot_ids,
            "user": user
        }
        
        # Call API to create the dataset and run evaluations
        with api_request("run_eval_dataset", method="POST", data=dataset_data, id_token=id_token) as r:
            r.raise_for_status()
            result = r.json()
            
            if result.get("message") == "Success" and "dataset_id" in result:
                flash(f"Evaluation dataset '{name}' created successfully! Evaluations are running in the background.", "success")
                return redirect(f"/eval-dataset/{result['dataset_id']}")
            else:
                flash(f"Failed to create evaluation dataset: {result.get('message', 'Unknown error')}", "error")
                return redirect("/create-eval-dataset")
                
    except Exception as e:
        logger.exception(f"Error creating evaluation dataset: {str(e)}")
        flash(f"Error creating evaluation dataset: {str(e)}", "error")
        return redirect("/create-eval-dataset")


@app.route("/eval-dataset/<dataset_id>", methods=["GET"])
def view_eval_dataset(dataset_id):
    """Page to view a specific evaluation dataset and compare outputs."""
    logger.info(f"View eval dataset endpoint called for dataset ID: {dataset_id}")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")
    
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    
    # Fetch the dataset details
    try:
        with api_request(f"get_dataset_sessions/{dataset_id}", method="GET", data={"user": user}, id_token=id_token) as r:
            if r.status_code == 200:
                dataset = r.json()
                if dataset.get("message") == "Success" and "dataset" in dataset:
                    # Get all available bots to retrieve bot names
                    bots = {}
                    try:
                        with api_request("view_bots", method="POST", data={"user": user}, id_token=id_token) as r:
                            if r.status_code == 200:
                                response_data = r.json()
                                if response_data.get("message") == "Success" and "data" in response_data:
                                    bots = response_data["data"]
                    except Exception:
                        logger.exception("Failed to fetch bots for eval dataset view")
                    
                    # Add bot names to the dataset
                    for session_id, session_info in dataset["dataset"]["sessions"].items():
                        bot_id = session_info.get("bot_id", "")
                        if bot_id in bots:
                            session_info["bot_name"] = bots[bot_id].get("name", "Unknown Bot")
                        else:
                            session_info["bot_name"] = f"Bot ID: {bot_id}"
                    return render_template("view_eval_dataset.html", 
                                          user=user, 
                                          dataset=dataset["dataset"], 
                                          bots=bots)
                else:
                    flash(f"Failed to fetch evaluation dataset: {dataset.get('message', 'Unknown error')}", "error")
            else:
                flash(f"Failed to fetch evaluation dataset: {r.status_code}", "error")
    except Exception as e:
        logger.exception(f"Error fetching evaluation dataset: {str(e)}")
        flash(f"Error fetching evaluation dataset: {str(e)}", "error")
    
    return redirect("/eval-datasets")

@app.route("/clone-eval-dataset/<dataset_id>", methods=["GET"])
def clone_eval_dataset(dataset_id):
    """Clone an existing evaluation dataset."""
    logger.info("Cloning evaluation dataset: %s", dataset_id)
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")
    
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    
    logger.info("Fetching dataset info for ID %s", dataset_id)
    try:
        with api_request(f"get_dataset_sessions/{dataset_id}", method="GET", id_token=id_token) as r:
            r.raise_for_status()
            result = r.json()
    except Exception:
        logger.exception("Fetch dataset info failed.")
        return jsonify({"error": "Failed to load dataset."}), 400
    
    logger.debug("Fetched dataset info: %s", result)
    if not result.get("dataset"):
        logger.error("Fetch dataset info received an unexpected response.")
        abort(404)
    
    dataset_data = result["dataset"]
    
    # Create a dataset object with the necessary fields
    dataset = {
        "name": dataset_data.get("name", ""),
        "description": dataset_data.get("description", ""),
        "inputs": dataset_data.get("inputs", []),
        "bot_ids": dataset_data.get("bot_ids", [])
    }
    
    # Get all available bots for selection
    bots = {}
    try:
        with api_request("view_bots", method="POST", data={"user": user}, id_token=id_token) as r:
            if r.status_code == 200:
                response_data = r.json()
                if response_data.get("message") == "Success" and "data" in response_data:
                    bots = response_data["data"]
                    logger.info(f"Fetched {len(bots)} bots for eval dataset creation")
    except Exception:
        logger.exception("Failed to fetch bots for eval dataset creation")
    
    return render_template("create_eval_dataset.html", user=user, bots=bots, dataset=dataset)

@app.route("/new-label-eval-dataset/<dataset_id>", methods=["GET"])
def new_label_eval_dataset(dataset_id):
    """Page to configure and create a labeled dataset."""
    logger.info(f"New label eval dataset endpoint called for dataset ID: {dataset_id}")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")
    
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    
    # Render the new template for configuring the labeled dataset
    return render_template("new_label_eval_pop.html", dataset_id=dataset_id, user=user)

# Add a new route to handle the form submission from new_label_eval_pop.html
@app.route("/create-labeled-dataset/<dataset_id>", methods=["POST"])
def create_labeled_dataset(dataset_id):
    """Create a labeled dataset with multiple aspects."""
    logger.info(f"Create labeled dataset endpoint called for dataset ID: {dataset_id}")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")
    
    # Get form data
    dataset_name = request.form.get('dataset_name')
    aspect_ids = request.form.getlist('aspect_ids[]')
    aspect_names = request.form.getlist('aspect_names[]')
    aspect_descriptions = request.form.getlist('aspect_descriptions[]')
    aspect_types = request.form.getlist('aspect_types[]')
    
    # Log the received form data for debugging
    logger.info(f"Received form data: name={dataset_name}, aspects count={len(aspect_ids)}")
    logger.info(f"Aspect IDs: {aspect_ids}")
    logger.info(f"Aspect Names: {aspect_names}")
    logger.info(f"Aspect Types: {aspect_types}")
    
    if not dataset_name or not aspect_ids:
        flash("Dataset name and at least one aspect are required", "error")
        return redirect(f"/new-label-eval-dataset/{dataset_id}")
    
    # Prepare data for API request - match the expected format
    labeling_aspects = []
    for i in range(len(aspect_ids)):
        aspect = {
            'aspect_id': aspect_ids[i],
            'name': aspect_names[i],
            'description': aspect_descriptions[i] if aspect_descriptions[i] else None,
            'type': aspect_types[i],
            # Add the optional fields with default values
            'rank_value': None,
            'thumbs_value': None,
            'score_value': None
        }
        labeling_aspects.append(aspect)
        logger.info(f"Added aspect: {aspect}")
    
    try:
        # Based on the validation error, FastAPI expects:
        # 1. dataset_name and dataset_id as query parameters
        # 2. The request body to be a list of labeling aspects
        import requests
        
        url = f"{api_url}/create_labeled_dataset"
        
        # Add query parameters
        params = {
            'dataset_name': dataset_name,
            'dataset_id': dataset_id
        }
        
        headers = {
            "Authorization": f"Bearer {id_token}",
            "Content-Type": "application/json"
        }
        
        # Send the labeling_aspects as the request body (which should be a list)
        logger.info(f"Making request to {url} with params={params}")
        logger.info(f"Request body (list): {labeling_aspects}")
        
        response = requests.post(url, headers=headers, params=params, json=labeling_aspects)
        
        logger.info(f"API response status: {response.status_code}")
        
        # Log the response content for debugging
        try:
            response_content = response.json()
            logger.info(f"API response content: {response_content}")
        except Exception as e:
            logger.error(f"Failed to parse response as JSON: {str(e)}")
            logger.info(f"Raw response content: {response.text}")
        
        if response.status_code == 422:
            # Handle validation errors specifically
            error_detail = "Unknown validation error"
            try:
                response_json = response.json()
                if "detail" in response_json:
                    error_detail = response_json["detail"]
            except Exception:
                pass
            
            logger.error(f"Validation error: {error_detail}")
            flash(f"Validation error: {error_detail}", "error")
            return redirect(f"/new-label-eval-dataset/{dataset_id}")
        
        if response.status_code != 200:
            logger.error(f"Failed to create labeled dataset: {response.status_code} - {response.text}")
            flash(f"Failed to create labeled dataset: {response.status_code}", "error")
            return redirect(f"/new-label-eval-dataset/{dataset_id}")
        
        result = response.json()
        if result.get("message") != "Success":
            flash(f"Failed to create labeled dataset: {result.get('message', 'Unknown error')}", "error")
            return redirect(f"/new-label-eval-dataset/{dataset_id}")
        elif "labeled_dataset_id" in result:
            # Redirect to the label-eval-dataset endpoint
            return redirect(f"/label-eval-dataset/{result['labeled_dataset_id']}")
        else:
            flash("Created labeled dataset but no ID was returned", "warning")
            return redirect("/labeled-eval-datasets")
    except Exception as e:
        logger.exception(f"Error creating labeled dataset: {str(e)}")
        flash(f"Error creating labeled dataset: {str(e)}", "error")
        return redirect(f"/new-label-eval-dataset/{dataset_id}")

@app.route("/labeled-eval-datasets", methods=["GET"])
def labeled_eval_datasets():
    """Page to view all labeled evaluation datasets."""
    logger.info("Labeled eval datasets endpoint called")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")
    
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    
    # Fetch all labeled datasets
    try:
        with api_request("get_user_labeled_datasets", method="GET", data={"user": user}, id_token=id_token) as r:
            if r.status_code == 200:
                result = r.json()
                if result.get("message") == "Success" and "datasets" in result:
                    return render_template("labeled_eval_datasets.html", 
                                          user=user, 
                                          labeled_datasets=result["datasets"])
                else:
                    flash(f"Failed to fetch labeled datasets: {result.get('message', 'Unknown error')}", "error")
            else:
                flash(f"Failed to fetch labeled datasets: {r.status_code}", "error")
    except Exception as e:
        logger.exception(f"Error fetching labeled datasets: {str(e)}")
        flash(f"Error fetching labeled datasets: {str(e)}", "error")
    
    return render_template("labeled_eval_datasets.html", user=user, labeled_datasets={})

@app.route("/label-eval-dataset/<dataset_id>", methods=["GET"])
def label_eval_dataset(dataset_id):
    """Page to label or edit labels for an evaluation dataset."""
    logger.info(f"Label eval dataset endpoint called for dataset ID: {dataset_id}")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")
    
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    
    # Fetch the dataset details
    try:
        with api_request(f"get_labeled_dataset/{dataset_id}", method="GET", data={"user": user}, id_token=id_token) as r:
            if r.status_code == 200:
                result = r.json()
                if result.get("message") == "Success" and "dataset" in result:
                    dataset = result["dataset"]
                    
                    # Get eval_type from the dataset
                    eval_type = dataset.get("labeling_type")
                    if not eval_type:
                        flash("Dataset does not have a label type specified", "error")
                        return redirect("/labeled-eval-datasets")
                    
                    # Get all available bots to retrieve bot names
                    bots = {}
                    try:
                        with api_request("view_bots", method="POST", data={"user": user}, id_token=id_token) as r:
                            if r.status_code == 200:
                                response_data = r.json()
                                if response_data.get("message") == "Success" and "data" in response_data:
                                    bots = response_data["data"]
                    except Exception:
                        logger.exception("Failed to fetch bots for labeled dataset view")
                    
                    return render_template("label_eval_dataset.html", 
                                          user=user, 
                                          dataset=dataset,
                                          dataset_id=dataset_id,
                                          eval_type=eval_type,
                                          bots=bots)
                else:
                    flash(f"Failed to fetch labeled dataset: {result.get('message', 'Unknown error')}", "error")
            else:
                flash(f"Failed to fetch labeled dataset: {r.status_code}", "error")
    except Exception as e:
        logger.exception(f"Error fetching labeled dataset: {str(e)}")
        flash(f"Error fetching labeled dataset: {str(e)}", "error")
    
    return redirect("/labeled-eval-datasets")

@app.route("/update-labeled-session/<dataset_id>", methods=["POST"])
def update_labeled_session_endpoint(dataset_id):
    """Update a single labeled session in an evaluation dataset."""
    logger.info(f"Update labeled session endpoint called for dataset ID: {dataset_id}")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    if not id_token:
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    
    # Get the label data from the request
    try:
        data = request.get_json()
        input_idx = data.get("input_idx")
        session_id = data.get("session_id")
        bot_id = data.get("bot_id")
        eval_type = data.get("eval_type")
        value = data.get("value")
        notes = data.get("notes")
        
        # If session_id is not provided, try to use input_idx for backward compatibility
        if session_id is None and input_idx is not None:
            logger.warning("Using input_idx as session_id for backward compatibility")
            session_id = input_idx
        
        # Validate required fields
        if session_id is None or eval_type is None:
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        # For rank type, we need to handle an array of bot IDs
        if eval_type == "rank":
            if not isinstance(value, list):
                return jsonify({"success": False, "message": "Ranking value must be an array of bot IDs"}), 400
            
            # Process each bot in the ranking
            success_count = 0
            error_count = 0
            error_messages = []
            
            for position, bot_id in enumerate(value):
                try:
                    api_data = {
                        "dataset_id": dataset_id,
                        "session_id": session_id,
                        "ranking": position + 1,  # Position is 1-indexed
                        "notes": notes,
                        "user": user
                    }
                    
                    with api_request("update_labeled_session", method="POST", data=api_data, id_token=id_token) as r:
                        if r.status_code == 200 and r.json().get("message") == "Success":
                            success_count += 1
                        else:
                            error_count += 1
                            error_messages.append(f"Failed to update rank for session {session_id} in dataset {dataset_id}")
                except Exception as e:
                    error_count += 1
                    error_messages.append(f"Error updating rank for session {session_id} in dataset {dataset_id}: {str(e)}")
            
            # Return a summary of the results
            if error_count == 0:
                return jsonify({
                    "success": True, 
                    "message": f"All rankings saved successfully ({success_count} updates)"
                })
            else:
                return jsonify({
                    "success": True, 
                    "message": f"Saved {success_count} rankings with {error_count} errors",
                    "errors": error_messages[:5]  # Return first 5 errors only to avoid huge responses
                })
        else:
            
            # Prepare data according to new structure
            api_data = {
                "user": user,
                "dataset_id": dataset_id,
                "session_id": session_id,
                "notes": notes
            }
            
            # Set the appropriate field based on eval_type
            if eval_type == "thumbs":
                api_data["thumbs_up"] = True if value == "up" else False
            elif eval_type == "score":
                try:
                    api_data["score"] = float(value)
                except (ValueError, TypeError):
                    return jsonify({"success": False, "message": "Score must be a valid number"}), 400
            
            # Call the API to update the labeled session
            with api_request("update_labeled_session", method="POST", data=api_data, id_token=id_token) as r:
                if r.status_code == 200:
                    result = r.json()
                    if result.get("message") == "Success":
                        return jsonify({"success": True, "message": "Label updated successfully"})
                    else:
                        return jsonify({"success": False, "message": result.get("message", "Unknown error")})
                else:
                    return jsonify({"success": False, "message": f"API error: {r.status_code}"}), r.status_code
    except Exception as e:
        logger.exception(f"Error updating label: {str(e)}")
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500