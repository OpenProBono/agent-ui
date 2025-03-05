import datetime
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
    email = session.get("email")
    return render_template("index.html", agents=agents, metrics=metrics, email=email)


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
    
    return render_template("agents.html", agents=agents)


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
    return render_template("resources.html", collections=collections, resources=resources)


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
    return render_template("users.html", users=example_data)


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
            data = {"session_id": session_id}
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


@app.route("/get_session_messages/<session_id>", methods=["GET"])
def get_session_messages(session_id):
    logger.info("Session messages endpoint called for session ID %s", session_id)
    id_token = session.get("id_token")
    if not id_token:
        return redirect("/signup")

    try:
        data = {"session_id": session_id}
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
    data = {
        "feedback_text": feedback_data["comment"],
        "session_id": session_id,
        "feedback_type": feedback_data["type"],
        "message_index": feedback_index,
        "categories": feedback_data["categories"] if feedback_data["type"] == "dislike" else [],
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
