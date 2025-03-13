import datetime
import os
import time
from json import dumps, loads
from typing import List
from functools import wraps

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
    url_for,
    make_response,
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
# Set session cookie to be secure in production and expire after 12 hours
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(hours=12)

# Dictionary of search methods with display names and descriptions
SEARCH_METHODS = {
    "dynamic_serpapi": {
        "display_name": "Dynamic Web Search (SerpAPI)",
        "description": "Uses SerpAPI to perform dynamic web searches with customizable parameters."
    },
    "courtlistener": {
        "display_name": "CourtListener",
        "description": "Specialized search for legal cases and court documents in the US using CourtListener."
    },
    "bailii": {
        "display_name": "BAILII",
        "description": "Specialized search for legal cases and court documents in the UK using BAILII."
    }
}

# Routes that don't require authentication
PUBLIC_ROUTES = [
    'static',
    'login',
    'login_page',
    'signup',
    'logout'
]

@app.before_request
def check_auth():
    """
    Middleware to check if user is authenticated before processing requests.
    Redirects to login page if not authenticated and not accessing a public route.
    Also handles token refresh to prevent redirect loops.
    """
    # Skip authentication check for public routes
    if request.endpoint in PUBLIC_ROUTES:
        return
    
    # Skip authentication for OPTIONS requests (CORS preflight)
    if request.method == 'OPTIONS':
        return
        
    # Check if user is authenticated
    id_token = session.get('id_token')
    if not id_token:
        # If AJAX request, return 401 Unauthorized
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
            return jsonify({'status': 'error', 'message': 'Authentication required', 'code': 'auth_required'}), 401
        
        # Get the current URL to redirect back after login
        next_url = request.url
        # Don't include the host in the URL
        if next_url.startswith(request.host_url):
            next_url = next_url[len(request.host_url.rstrip('/')):]
        
        # Otherwise redirect to login page with a clear message
        flash("Please log in to continue.", "info")
        return redirect(url_for('login_page', redirect_to=next_url))
    
    # Check if token needs refresh
    if should_refresh_token():
        try:
            # Try to refresh the token
            refreshed = refresh_token()
            if not refreshed:
                # If refresh failed, clear the session and redirect to login
                session.clear()
                # If AJAX request, return 401 Unauthorized
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
                    return jsonify({'status': 'error', 'message': 'Session expired. Please log in again.', 'code': 'session_expired'}), 401
                
                # Get the current URL to redirect back after login
                next_url = request.url
                # Don't include the host in the URL
                if next_url.startswith(request.host_url):
                    next_url = next_url[len(request.host_url.rstrip('/')):]
                
                # Otherwise redirect to login page with a clear message
                flash("Your session has expired. Please log in again.", "warning")
                return redirect(url_for('login_page', redirect_to=next_url))
        except Exception as e:
            logger.exception("Token refresh failed")
            session.clear()
            # If AJAX request, return 401 Unauthorized
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
                return jsonify({'status': 'error', 'message': 'Authentication error. Please log in again.', 'code': 'auth_error'}), 401
            
            # Get the current URL to redirect back after login
            next_url = request.url
            # Don't include the host in the URL
            if next_url.startswith(request.host_url):
                next_url = next_url[len(request.host_url.rstrip('/')):]
            
            # Otherwise redirect to login page with a clear message
            flash("Authentication error. Please log in again.", "error")
            return redirect(url_for('login_page', redirect_to=next_url))

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        id_token = session.get("id_token")
        
        if not id_token:
            # Get the current URL to redirect back after login
            next_url = request.url
            # Don't include the host in the URL
            if next_url.startswith(request.host_url):
                next_url = next_url[len(request.host_url.rstrip('/')):]
                
            # User is not logged in, redirect to login page
            flash("Please log in to continue.", "info")
            return redirect(url_for('login_page', redirect_to=next_url))
        
        # Token refresh is now handled by the check_auth middleware
        # so we can just proceed with the function call
        return f(*args, **kwargs)
    return decorated_function

def should_refresh_token():
    """
    Check if the token needs to be refreshed based on expiration time.
    Uses a timestamp-based approach to avoid decoding JWT on every request.
    """
    token_timestamp = session.get("token_timestamp")
    
    # If no timestamp exists, token should be refreshed
    if token_timestamp is None:
        return True
    
    try:
        # Convert to float if it's a string
        if isinstance(token_timestamp, str):
            token_timestamp = float(token_timestamp)
        
        # Firebase ID tokens expire after 1 hour, refresh if older than 55 minutes
        return (time.time() - token_timestamp) > (55 * 60)
    except (ValueError, TypeError):
        logger.exception("Invalid token timestamp format")
        # If we can't parse the timestamp, assume token needs refresh
        return True

def refresh_token():
    """
    Refresh the Firebase authentication token using the refresh token.
    Returns True if successful, False otherwise.
    """
    refresh_token_value = session.get("refresh_token")
    if not refresh_token_value:
        logger.warning("No refresh token available in session")
        return False
    
    try:
        # Use Firebase Auth REST API to refresh the token
        firebase_api_key = os.environ.get("FIREBASE_API_KEY")
        if not firebase_api_key:
            logger.error("FIREBASE_API_KEY environment variable not set")
            return False
            
        refresh_url = f"https://securetoken.googleapis.com/v1/token?key={firebase_api_key}"
        refresh_payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token_value
        }
        
        logger.info("Attempting to refresh Firebase token")
        response = requests.post(refresh_url, json=refresh_payload, timeout=10)
        
        if response.status_code == 200:
            response_data = response.json()
            if "id_token" in response_data:
                # Update session with new tokens
                session["id_token"] = response_data["id_token"]
                session["refresh_token"] = response_data.get("refresh_token", refresh_token_value)
                session["token_timestamp"] = time.time()
                logger.info("Successfully refreshed Firebase token")
                return True
            else:
                logger.warning("Firebase token refresh response missing id_token")
                return False
                
        # Log specific error codes for better debugging
        if response.status_code == 400:
            logger.warning("Firebase token refresh failed: Invalid refresh token (400)")
        elif response.status_code == 401:
            logger.warning("Firebase token refresh failed: Unauthorized (401)")
        elif response.status_code == 403:
            logger.warning("Firebase token refresh failed: Forbidden (403)")
        else:
            logger.warning(f"Failed to refresh token: {response.status_code} - {response.text}")
        return False
    except requests.exceptions.Timeout:
        logger.warning("Firebase token refresh request timed out")
        return False
    except Exception:
        logger.exception("Token refresh request failed")
        return False

def fetch_sessions_api(user, id_token) -> List[dict]:
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
    return sessions

@app.route("/signup")
def signup():
    logger.info("Signup endpoint called.")
    # If user is already logged in, redirect to dashboard
    if session.get("id_token"):
        return redirect(url_for("agents"))
    return render_template("signup.html")

@app.route("/login", methods=["GET"])
def login_page():
    logger.info("Login page endpoint called.")
    
    # Get the redirect_to parameter if it exists
    redirect_to = request.args.get('redirect_to', url_for('agents'))
    
    # Check if there's a valid token that doesn't need refresh
    id_token = session.get("id_token")
    if id_token and not should_refresh_token():
        # User is already logged in with a valid token, redirect to dashboard or requested page
        logger.info("User already logged in, redirecting to: %s", redirect_to)
        return redirect(redirect_to)
    
    # If token exists but needs refresh, try to refresh it
    if id_token and should_refresh_token():
        try:
            refreshed = refresh_token()
            if refreshed:
                # Successfully refreshed, redirect to dashboard or requested page
                logger.info("Token refreshed, redirecting to: %s", redirect_to)
                return redirect(redirect_to)
            else:
                # Failed to refresh, clear session
                session.clear()
                flash("Your session has expired. Please log in again.", "warning")
        except Exception:
            # Error refreshing, clear session
            logger.exception("Error refreshing token on login page")
            session.clear()
            flash("Authentication error. Please log in again.", "error")
    
    # Pass the redirect_to parameter to the template
    return render_template("signup.html", redirect_to=redirect_to)

@app.route("/login", methods=["POST"])
def login():
    logger.info("Login endpoint called.")
    try:
        # Get authentication data from request
        data = request.get_json()
        if not data:
            logger.error("No JSON data in login request")
            return jsonify({"status": "error", "message": "Invalid request format"}), 400
        
        # Clear any existing session data to prevent stale data
        session.clear()
            
        # Store user information in session
        session["email"] = data.get("email")
        session["firebase_uid"] = data.get("firebase_uid")
        session["id_token"] = data.get("idToken")
        session["refresh_token"] = data.get("refreshToken")
        session["token_timestamp"] = time.time()
        session.permanent = True  # Use the permanent session lifetime we configured
        
        # Get the redirect_to parameter if it exists
        redirect_to = data.get("redirect_to", url_for("agents"))
        
        logger.info(f"User logged in: {session['email']}, redirecting to: {redirect_to}")
        # Return success response with the redirect URL
        return jsonify({"status": "success", "redirect": redirect_to})
    except Exception as e:
        logger.exception("Login error")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/logout")
def logout():
    logger.info("Logout endpoint called.")
    # Get the current user email for logging purposes
    user_email = session.get("email", "Unknown user")
    
    # Clear all session data
    session.clear()
    
    logger.info(f"User logged out: {user_email}")
    
    # Return a page with JavaScript to sign out from Firebase
    # Add a parameter to indicate this is an explicit logout
    return render_template("logout.html", explicit_logout=True)

@app.route("/")
@app.route("/index")
@app.route("/dashboard")
@app.route("/agents")
@login_required
def agents():
    logger.info("Agents endpoint called.")

    # Get the user's ID token from the session
    id_token = session.get("id_token")
    user = {"firebase_uid": session.get("firebase_uid"), "email": session.get("email")}
    # Initialize agents list
    agents = []
    public_agents = []

    try:
        # Fetch user's bots
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

                        # Format the created_on date
                        created_on = datetime.datetime.now()
                        if "timestamp" in bot and bot["timestamp"]:
                            try:
                                if isinstance(bot["timestamp"], dict) and "seconds" in bot["timestamp"]:
                                    created_on = datetime.datetime.fromtimestamp(bot["timestamp"]["seconds"])
                                else:
                                    created_on = datetime.datetime.fromisoformat(str(bot["timestamp"]))
                            except (ValueError, TypeError):
                                pass

                        # Store the raw timestamp for client-side formatting
                        agent = {
                            "id": bot_id,
                            "name": bot.get("name", "Untitled Bot"),
                            "created_on": created_on.isoformat(),
                            "tools": total_tools,
                        }
                        agents.append(agent)
            else:
                logger.error(f"Failed to fetch agents: {r.status_code} - {r.text}")
        
        # Fetch public bots
        with api_request("view_public_bots", method="POST", data={"user": user}, id_token=id_token) as r:
            if r.status_code == 200:
                response_data = r.json()
                if response_data.get("message") == "Success" and "data" in response_data:
                    # Transform the API response to match the expected format for the template
                    for bot_id, bot in response_data["data"].items():
                        # Skip if this bot is already in the user's personal bots
                        if any(a["id"] == bot_id for a in agents):
                            continue
                            
                        # Count total tools (search_tools + vdb_tools)
                        search_tools = bot.get("search_tools", [])
                        vdb_tools = bot.get("vdb_tools", [])
                        total_tools = len(search_tools) + len(vdb_tools)

                        # Format the created_on date
                        created_on = datetime.datetime.now()
                        if "timestamp" in bot and bot["timestamp"]:
                            try:
                                if isinstance(bot["timestamp"], dict) and "seconds" in bot["timestamp"]:
                                    created_on = datetime.datetime.fromtimestamp(bot["timestamp"]["seconds"])
                                else:
                                    created_on = datetime.datetime.fromisoformat(str(bot["timestamp"]))
                            except (ValueError, TypeError):
                                pass

                        # Store the raw timestamp for client-side formatting
                        agent = {
                            "id": bot_id,
                            "name": bot.get("name", "Untitled Bot"),
                            "created_on": created_on.isoformat(),
                            "tools": total_tools,
                        }
                        public_agents.append(agent)
            else:
                logger.error(f"Failed to fetch public agents: {r.status_code} - {r.text}")
    except Exception as e:
        logger.exception(f"Error fetching agents: {str(e)}")

    # If no agents were fetched (either due to error or user not authenticated),
    # provide example data for display purposes
    if not agents:
        logger.warning("No agents found for user.")
        # Empty list will be passed to template
    
    if not public_agents:
        logger.warning("No public agents found.")
        # Empty list will be passed to template

    return render_template("agents.html", agents=agents, public_agents=public_agents, user=user)


@app.route("/resources")
@login_required
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
@login_required
def chatbot(agent, session_id=None):
    user = {"firebase_uid": session.get("firebase_uid"), "email": session.get("email")}
    data = {"bot_id": agent, "user": user}
    logger.info("Fetching agent info for ID %s", agent)
    id_token = session.get("id_token")

    try:
        with api_request("view_bot", method="POST", id_token=id_token, params=data) as r:
            r.raise_for_status()
            result = r.json()
    except Exception:
        logger.exception("Fetch agent info failed.")
        return jsonify({"error": "Failed to load agent."}), 400
    logger.info("Fetched agent info: %s", result)
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
    name = result["data"].get("name") if result["data"].get("name") else None
    logger.info("Agent name: %s", name)
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
@login_required
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
@login_required
def chat():
    logger.info("Chat endpoint called.")
    id_token = session.get("id_token")
    user = {"firebase_uid": session.get("firebase_uid"), "email": session.get("email")}

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
@login_required
def new_session(agent):
    logger.info("Starting new session for agent ID %s", agent)
    id_token = session.get("id_token")
    user = {"firebase_uid": session.get("firebase_uid"), "email": session.get("email")}
    try:
        with api_request("initialize_session", id_token=id_token, data={"bot_id": agent, "user": user}) as r:
            r.raise_for_status()
            return jsonify(r.json())
    except Exception:
        logger.exception("New session error occurred.")
        return jsonify({"error": "Failed to create session."}), 400


@app.route("/agent/<agent>/info", methods=["GET"])
@login_required
def agent_info(agent):
    data = {"bot_id": agent}
    logger.info("Agent info endpoint called for ID %s", agent)
    id_token = session.get("id_token")

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
    # logger.debug("Agent endpoint info got response: %s", result)
    return jsonify(result)


@app.route("/sessions", methods=["GET"])
@login_required
def get_sessions():
    try:
        logger.info("Sessions endpoint called.")
        id_token = session.get("id_token")
        
        user = {"firebase_uid": session.get("firebase_uid"), "email": session.get("email")}
        sessions = fetch_sessions_api(user, id_token)
        # logger.info("Sessions endpoint got responses: %s", sessions)
        return jsonify(sessions)
    except Exception:
        logger.exception("Sessions endpoint got an unexpected response.")
        return jsonify({"error": "Failed to fetch sessions."}), 400


@app.route("/sessions-page", methods=["GET"])
@login_required
def sessions_page():
    """Page to view all the user's previous chat sessions with filtering capability."""
    logger.info("Sessions page endpoint called.")

    # Get the user's ID token from the session
    id_token = session.get("id_token")
    user = {"firebase_uid": session.get("firebase_uid"), "email": session.get("email")}

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
    sessions = fetch_sessions_api(user, id_token)

    return render_template("sessions.html", user=user, bots=bots, sessions=sessions)


@app.route("/get_session_messages/<session_id>", methods=["GET"])
@login_required
def get_session_messages(session_id):
    logger.info("Session messages endpoint called for session ID %s", session_id)
    id_token = session.get("id_token")

    try:
        user = {"firebase_uid": session.get("firebase_uid"), "email": session.get("email")}
        data = {"session_id": session_id, "user": user}
        with api_request("fetch_session_formatted_history", id_token=id_token, data=data) as r:
            r.raise_for_status()
            session_data = r.json()
            # logger.debug("Session messages endpoint got response: %s", session_data)
            return jsonify(session_data)
    except Exception:
        logger.exception("Session messages endpoint got an unexpected response.")
        return jsonify({"error": "Failed to fetch messages."}), 400


@app.route("/status", methods=["GET"])
@login_required
def get_status():
    logger.info("Status endpoint called.")
    id_token = session.get("id_token")
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


@app.route("/available_models", methods=["GET"])
@login_required
def get_available_models():
    logger.info("Available models endpoint called")
    id_token = session.get("id_token")

    try:
        with api_request("available_models", method="GET", id_token=id_token) as r:
            r.raise_for_status()
            return jsonify(r.json())
    except Exception:
        logger.exception("Failed to get available models")
        return jsonify({"message": "Error", "data": {}})


@app.route("/feedback", methods=["POST"])
@login_required
def feedback():
    logger.info("Feedback endpoint called.")
    id_token = session.get("id_token")

    feedback_data = loads(request.form.get("data"))
    feedback_index = request.form.get("index")
    session_id = request.form.get("sessionId")
    user = {"firebase_uid": session.get("firebase_uid"), "email": session.get("email")}
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
@login_required
def search(collection):
    start = time.time()
    id_token = session.get("id_token")
    email = session.get("email")
    uid = session.get("firebase_uid")
    user = {"email": email, "firebase_uid": uid}
    if not collection:
        abort(404)
    semantic = request.args.get("semantic")
    if not semantic:
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
@login_required
def manage(collection):
    start = time.time()
    if not collection:
        abort(404)
    id_token = session.get("id_token")
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
@login_required
def get_resource_count(collection_name) -> int:
    logger.info("Getting resource count for collection %s.", collection_name)
    id_token = session.get("id_token")
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
@login_required
def fetch_summary(resource_id):
    logger.info("Fetching summary for %s.", resource_id)
    id_token = session.get("id_token")
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
@login_required
def create_agent():
    logger.info("Create agent endpoint called.")
    id_token = session.get("id_token")
    user = {"firebase_uid": session.get("firebase_uid"), "email": session.get("email")}
    if request.method == "GET":
        return render_template("create_agent.html", user=user, search_methods=SEARCH_METHODS)
    # Retrieve core fields
    bot_name = request.form.get("bot_name", None)
    system_prompt = request.form.get("system_prompt", None)
    message_prompt = request.form.get("message_prompt", None)
    search_names = request.form.getlist("search_names[]")
    search_methods = request.form.getlist("search_methods[]")
    search_prefixes = request.form.getlist("search_prefixes[]")
    search_prompts = request.form.getlist("search_prompts[]")

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

    # Chat model configuration
    chat_model = {
        "engine": request.form.get("engine", "openai"),
        "model": request.form.get("model", "gpt-4o"),
        "temperature": float(request.form.get("temperature", 0)),
        "seed": int(request.form.get("seed", 0)),
    }

    # Prepare the data for the API request
    data = {
        "name": bot_name,
        "system_prompt": system_prompt,
        "message_prompt": message_prompt,
        "search_tools": search_tools,
        "vdb_tools": [],  # Empty VDB tools list
        "chat_model": chat_model,
        "user": user,
        "public": False  # Always set to False
    }

    try:
        with api_request("create_bot", method="POST", data=data, id_token=id_token) as r:
            r.raise_for_status()
            result = r.json()
            logger.info("Created bot with ID: %s", result.get("bot_id"))
            flash(f"Agent '{bot_name}' created successfully!", "success")
            return redirect(f"/agent/{result.get('bot_id')}")
    except Exception:
        logger.exception("Create agent failed.")
        flash("Failed to create agent. Please try again.", "error")
        return redirect("/create-agent")


@app.route("/clone/<agent>", methods=["GET"])
@login_required
def clone_agent(agent):
    logger.info("Cloning agent: %s", agent)
    data = {"bot_id": agent}
    id_token = session.get("id_token")

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
    return render_template("create_agent.html", clone=True, agent=agent, user=user, search_methods=SEARCH_METHODS)


@app.route("/delete-agent/<agent_id>", methods=["GET"])
@login_required
def delete_agent(agent_id):
    logger.info("Delete agent endpoint called for agent ID: %s", agent_id)

    # Get the user's ID token from the session
    id_token = session.get("id_token")

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
                    error_msg = f"Failed to delete agent: {response_data['message']}"
                    logger.error(error_msg)
                    flash(error_msg, "error")
            else:
                error_msg = f"Failed to delete agent: {r.status_code}"
                try:
                    error_data = r.json()
                    if "message" in error_data:
                        error_msg = error_data["message"]
                except Exception:
                    logger.exception("Failed to delete agent.")
                logger.error("Failed to delete agent: %s - %s", r.status_code, r.text)
                flash(error_msg, "error")
    except Exception as e:
        logger.exception("Exception while deleting agent.")
        flash(f"Error deleting agent: {e!s}", "error")

    # Redirect back to the agents page
    return redirect("/agents")


@app.route("/export_sessions", methods=["POST"])
@login_required
def export_sessions():
    """Export multiple sessions with their full data including messages."""
    logger.info("Export sessions endpoint called.")

    # Get the user's ID token from the session
    id_token = session.get("id_token")
    
    # Get user info
    user = {"firebase_uid": session.get("firebase_uid"), "email": session.get("email")}

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
                except Exception:
                    logger.exception("Error fetching messages for session %s.", session_id)
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

            except Exception:
                logger.exception("Error exporting session %s", session_id)
                # Continue with other sessions even if one fails

        if not exported_sessions:
            return jsonify({"error": "Failed to export any sessions"}), 500

        return jsonify({
            "message": "Success",
            "count": len(exported_sessions),
            "sessions": exported_sessions
        })

    except Exception:
        logger.exception("Export sessions endpoint error.")
        return jsonify({"error": "Failed to export sessions"}), 500

@app.route("/eval-datasets", methods=["GET"])
@login_required
def eval_datasets():
    """Page to view all evaluation datasets."""
    logger.info("Eval datasets endpoint called.")

    # Get the user's ID token from the session
    id_token = session.get("id_token")
    
    user = {"firebase_uid": session.get("firebase_uid"), "email": session.get("email")}

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
        logger.exception("Failed to fetch evaluation datasets for user.")

    return render_template("eval_datasets.html", user=user, datasets=datasets)


@app.route("/create-eval-dataset", methods=["GET", "POST"])
@login_required
def create_eval_dataset():
    """Page to create a new evaluation dataset."""
    logger.info("Create eval dataset endpoint called.")

    # Get the user's ID token from the session
    id_token = session.get("id_token")
    
    user = {"firebase_uid": session.get("firebase_uid"), "email": session.get("email")}

    if request.method == "GET":
        # Get all available bots for selection
        bots = {}
        try:
            with api_request("view_bots", method="POST", data={"user": user}, id_token=id_token) as r:
                if r.status_code == 200:
                    response_data = r.json()
                    if response_data.get("message") == "Success" and "data" in response_data:
                        bots = response_data["data"]
                        logger.info("Fetched %s bots for eval dataset creation", len(bots))
        except Exception:
            logger.exception("Failed to fetch bots for eval dataset creation.")

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
        logger.exception("Error creating evaluation dataset.")
        flash(f"Error creating evaluation dataset: {e!s}", "error")
        return redirect("/create-eval-dataset")


@app.route("/eval-dataset/<dataset_id>", methods=["GET"])
@login_required
def view_eval_dataset(dataset_id):
    """Page to view a specific evaluation dataset and compare outputs."""
    logger.info(f"View eval dataset endpoint called for dataset ID: {dataset_id}")

    # Get the user's ID token from the session
    id_token = session.get("id_token")
    
    user = {"firebase_uid": session.get("firebase_uid"), "email": session.get("email")}

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
        logger.exception("Error fetching evaluation dataset.")
        flash(f"Error fetching evaluation dataset: {e!s}", "error")

    return redirect("/eval-datasets")

@app.route("/clone-eval-dataset/<dataset_id>", methods=["GET"])
@login_required
def clone_eval_dataset(dataset_id):
    """Clone an existing evaluation dataset."""
    logger.info("Cloning evaluation dataset: %s", dataset_id)

    # Get the user's ID token from the session
    id_token = session.get("id_token")
    
    user = {"firebase_uid": session.get("firebase_uid"), "email": session.get("email")}

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
@login_required
def new_label_eval_dataset(dataset_id):
    """Page to configure and create a labeled dataset."""
    logger.info(f"New label eval dataset endpoint called for dataset ID: {dataset_id}")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    
    # Render the new template for configuring the labeled dataset
    return render_template("new_label_eval_pop.html", dataset_id=dataset_id, user=user)

# Add a new route to handle the form submission from new_label_eval_pop.html
@app.route("/create-labeled-dataset/<dataset_id>", methods=["POST"])
@login_required
def create_labeled_dataset(dataset_id):
    """Create a labeled dataset with multiple aspects."""
    logger.info(f"Create labeled dataset endpoint called for dataset ID: {dataset_id}")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    
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
@login_required
def labeled_eval_datasets():
    """Page to view all labeled evaluation datasets."""
    logger.info("Labeled eval datasets endpoint called")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    
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
@login_required
def label_eval_dataset(dataset_id):
    """Page to label or edit labels for an evaluation dataset."""
    logger.info(f"Label eval dataset endpoint called for dataset ID: {dataset_id}")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    
    # Fetch the dataset details
    try:
        with api_request(f"get_labeled_dataset/{dataset_id}", method="GET", data={"user": user}, id_token=id_token) as r:
            if r.status_code == 200:
                result = r.json()
                if result.get("message") == "Success" and "dataset" in result:
                    dataset = result["dataset"]
                    
                    # Fetch bot details for each bot in the dataset
                    bots = {}
                    for bot_id in dataset.get("bot_ids", []):
                        try:
                            with api_request(f"get_bot/{bot_id}", method="GET", data={"user": user}, id_token=id_token) as bot_r:
                                if bot_r.status_code == 200:
                                    bot_result = bot_r.json()
                                    if bot_result.get("message") == "Success" and "bot" in bot_result:
                                        bots[bot_id] = bot_result["bot"]
                        except Exception as e:
                            logger.warning(f"Error fetching bot {bot_id}: {str(e)}")
                    
                    # Check if labeling_aspects exists
                    if "labeling_aspects" not in dataset or not dataset["labeling_aspects"]:
                        flash("This dataset does not have any labeling aspects defined", "error")
                        return redirect("/labeled-eval-datasets")
                    
                    return render_template("label_eval_dataset.html", 
                                          user=user, 
                                          dataset=dataset,
                                          dataset_id=dataset_id,
                                          bots=bots)
                else:
                    flash(f"Failed to fetch dataset: {result.get('message', 'Unknown error')}", "error")
            else:
                flash(f"Failed to fetch dataset: {r.status_code}", "error")
    except Exception as e:
        logger.exception(f"Error fetching dataset: {str(e)}")
        flash(f"Error fetching dataset: {str(e)}", "error")
    
    return redirect("/labeled-eval-datasets")

@app.route("/update-labeled-session/<dataset_id>", methods=["POST"])
@login_required
def update_labeled_session_endpoint(dataset_id):
    """Update a single labeled session in an evaluation dataset."""
    logger.info(f"Update labeled session endpoint called for dataset ID: {dataset_id}")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    
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
        aspect_id = data.get("aspect_id")
        
        # Validate required fields
        if session_id is None or eval_type is None or aspect_id is None:
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
                        "user": user,
                        "dataset_id": dataset_id,
                        "session_id": session_id,
                        "aspect_id": aspect_id,
                        "ranking": position + 1,  # Position is 1-indexed
                        "notes": notes
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
                "aspect_id": aspect_id,
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

@app.route("/input_generator", methods=["POST"])
@login_required
def input_generator():
    """Generate inputs using AI based on a prompt."""
    logger.info("Input generator endpoint called.")
    
    # Get the user's ID token from the session
    id_token = session.get("id_token")
    
    user = {'firebase_uid': session.get("firebase_uid"), "email": session.get("email")}
    
    try:
        # Get the prompt from the request
        data = request.get_json()
        if not data or 'prompt' not in data:
            return jsonify({"message": "Missing prompt parameter"}), 400
        
        prompt = data['prompt']
        
        # Call the FastAPI input_generator endpoint
        with api_request("input_generator", method="POST", data={"prompt": prompt, "user": user}, id_token=id_token) as r:
            r.raise_for_status()
            result = r.json()
            
            if result.get("message") == "Success" and "inputs" in result:
                return jsonify({
                    "message": "Success",
                    "inputs": result["inputs"]
                })
            else:
                return jsonify({"message": result.get("message", "Failed to generate inputs")}), 400
                
    except Exception as e:
        logger.exception(f"Error generating inputs: {str(e)}")
        return jsonify({"message": f"Error: {str(e)}"}), 500