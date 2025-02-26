import datetime
import re
import time

from flask import abort, Flask, jsonify, request, flash, redirect, url_for,render_template, Response
from html import escape
from json import dumps, loads
from markdown import markdown
import logging
import requests
import os


app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

formatter = logging.Formatter("%(asctime)s %(levelname)s %(funcName)s %(message)s")
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("logger")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

API_URL = os.environ["OPB_API_URL"]
API_KEY = os.environ["OPB_TEST_API_KEY"]
HEADERS = {"X-API-KEY": API_KEY}

JURISDICTIONS = [
    {'display': 'Federal Appellate', 'value': 'us-app'},
    {'display': 'Federal District', 'value': 'us-dis'},
    {'display': 'Federal Supreme Court', 'value': 'us-sup'},
    {'display': 'Federal Special', 'value': 'us-misc'},
    {'display': 'Alabama', 'value': 'al'},
    {'display': 'Alaska', 'value': 'ak'},
    {'display': 'Arizona', 'value': 'az'},
    {'display': 'Arkansas', 'value': 'ar'},
    {'display': 'California', 'value': 'ca'},
    {'display': 'Colorado', 'value': 'co'},
    {'display': 'Connecticut', 'value': 'ct'},
    {'display': 'Delaware', 'value': 'de'},
    {'display': 'District of Columbia', 'value': 'dc'},
    {'display': 'Florida', 'value': 'fl'},
    {'display': 'Georgia', 'value': 'ga'},
    {'display': 'Hawaii', 'value': 'hi'},
    {'display': 'Idaho', 'value': 'id'},
    {'display': 'Illinois', 'value': 'il'},
    {'display': 'Indiana', 'value': 'in'},
    {'display': 'Iowa', 'value': 'ia'},
    {'display': 'Kansas', 'value': 'ks'},
    {'display': 'Kentucky', 'value': 'ky'},
    {'display': 'Louisiana', 'value': 'la'},
    {'display': 'Maine', 'value': 'me'},
    {'display': 'Maryland', 'value': 'md'},
    {'display': 'Massachusetts', 'value': 'ma'},
    {'display': 'Michigan', 'value': 'mi'},
    {'display': 'Minnesota', 'value': 'mn'},
    {'display': 'Mississippi', 'value': 'ms'},
    {'display': 'Missouri', 'value': 'mo'},
    {'display': 'Montana', 'value': 'mt'},
    {'display': 'Nebraska', 'value': 'ne'},
    {'display': 'Nevada', 'value': 'nv'},
    {'display': 'New Hampshire', 'value': 'nh'},
    {'display': 'New Jersey', 'value': 'nj'},
    {'display': 'New Mexico', 'value': 'nm'},
    {'display': 'New York', 'value': 'ny'},
    {'display': 'North Carolina', 'value': 'nc'},
    {'display': 'North Dakota', 'value': 'nd'},
    {'display': 'Ohio', 'value': 'oh'},
    {'display': 'Oklahoma', 'value': 'ok'},
    {'display': 'Oregon', 'value': 'or'},
    {'display': 'Pennsylvania', 'value': 'pa'},
    {'display': 'Rhode Island', 'value': 'ri'},
    {'display': 'South Carolina', 'value': 'sc'},
    {'display': 'South Dakota', 'value': 'sd'},
    {'display': 'Tennessee', 'value': 'tn'},
    {'display': 'Texas', 'value': 'tx'},
    {'display': 'Utah', 'value': 'ut'},
    {'display': 'Vermont', 'value': 'vt'},
    {'display': 'Virginia', 'value': 'va'},
    {'display': 'Washington', 'value': 'wa'},
    {'display': 'West Virginia', 'value': 'wv'},
    {'display': 'Wisconsin', 'value': 'wi'},
    {'display': 'Wyoming', 'value': 'wy'}
]

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
        "file_storage_used": "2 GB"
    }
    return render_template("index.html", agents=agents, metrics=metrics)


@app.route('/signup')
def signup():
    # firebase_config = {
    #     "apiKey": os.environ.get('FIREBASE_API_KEY'),
    #     "authDomain": os.environ.get('FIREBASE_AUTH_DOMAIN'),
    #     "projectId": os.environ.get('FIREBASE_PROJECT_ID')
    # }
    # return render_template('index.html', firebase_config=firebase_config)
    return render_template('signup.html')

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
    name = ' '.join(word.capitalize() for word in agent.split('_'))
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


def format_str(text: str) -> str:
    """Replace '\\n\\n' and with <br> and ¶ with '<br>¶'."""
    def replace_with_br(match):
        return f'<br>{match.group(0)}'

    pattern = r'\s(\S*¶\S*)'
    # \s matches any whitespace character
    # (\S*¶\S*) is a capture group that matches:
    #   - \S* : zero or more non-whitespace characters
    #   - ¶ : the paragraph character
    return re.sub(pattern, replace_with_br, text.replace("\n\n","<br>"))

def mark_keyword(text, keyword):
    # Split the keyword into individual words
    keywords = keyword.split()
    
    # Create a pattern to match the full keyword phrase first
    phrases_pattern = r'\b' + re.escape(keyword) + r'\b'
    phrases_compiled = re.compile(phrases_pattern, re.IGNORECASE)
    
    def replace_func(match):
        return f'<mark>{match.group()}</mark>'
    
    # First, mark the full keyword phrase
    text = phrases_compiled.sub(replace_func, text)
    
    # Create a pattern to match individual words only if they are standalone
    words_pattern = r'\b' + r'\b|\b'.join(re.escape(word) for word in keywords) + r'\b'
    words_compiled = re.compile(words_pattern, re.IGNORECASE)
    
    # Mark individual words only if the full phrase is not marked
    text = words_compiled.sub(lambda match: match.group() if f'<mark>{match.group()}</mark>' in text else replace_func(match), text)
    
    return text

def format_summary(summary):
    # Split the summary into lines
    lines = summary.split('\n')
    
    # Process each line
    formatted_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Check if the line contains a title (wrapped in asterisks)
        title_match = re.search(r'\*\*(.*?)\*\*', line)
        if title_match:
            # Extract the title
            title = title_match.group(1)
            # Replace the entire **title** part with HTML strong tags
            line = re.sub(r'\*\*.*?\*\*', f'<strong>{title}</strong>', line)
            # Remove leading dash if present
            line = re.sub(r'^- ?', '', line)
        
        formatted_lines.append(line)
    
    # Join the lines with line breaks
    return '<br>'.join(formatted_lines)


def generate_source_context(source, index, entities, keyword=None):
    source_type = source['type']
    context = {
        'index': index + 1,
        'type': source_type,
        'entities': process_entities(entities, keyword=keyword),
        'num_entities': len(entities),
    }
    meta = entities[0]['metadata']
    if source_type == 'opinion':
        context.update({
            'case_name': truncate_text(meta.get('case_name', ''), 150),
            'court_name': meta.get('court_name', ''),
            'url': f"https://www.courtlistener.com/opinion/{meta.get('cluster_id', '')}/{meta.get('slug', '')}",
            'author_info': get_author_info(meta),
            'opinion_type': get_opinion_type(meta.get('type', '')),
            'download_url': meta.get('download_url'),
            'courtlistener_summary': meta.get('summary'),
            'ai_summary': markdown(meta.get('ai_summary', '')) if meta.get('ai_summary') else None,
            'other_dates': meta.get('other_dates')
        })
    elif source_type == 'url':
        context.update({
            'url': source['id'],
            'source': meta.get('source', source['id']),
            'title': meta.get('title', 'Title Not Found'),
            'ai_summary': markdown(meta.get('ai_summary', '')) if meta.get('ai_summary') else None,
        })
        epoch_time = meta.get('timestamp', None)
        if epoch_time:
            date_object = datetime.datetime.fromtimestamp(meta.get('timestamp'), tz=datetime.UTC)
            formatted_date = date_object.strftime('%Y-%m-%d')
            context['timestamp'] = format_date(formatted_date)
    elif source_type == 'file':
        context.update({
            'filename': source['id'],
            'file_icon': get_file_icon(source['id'])
        })
        epoch_time = meta.get('timestamp', None)
        if epoch_time:
            date_object = datetime.datetime.fromtimestamp(meta.get('timestamp'), tz=datetime.UTC)
            formatted_date = date_object.strftime('%Y-%m-%d')
            context['timestamp'] = format_date(formatted_date)
    return context

def process_entities(entities, keyword=None):
    processed = []
    for entity in entities:
        text = escape(entity['text'])
        if keyword:
            text = mark_keyword(text, keyword)
        text = text.replace('\n', '<br>')
        processed_entity = {'text': text}
        if 'distance' in entity:
            processed_entity['match_score'] = round(max([0, (2 - entity['distance']) / 2]), 8)
        if 'page_number' in entity['metadata']:
            processed_entity['page_number'] = entity['metadata']['page_number']
        processed.append(processed_entity)
    return processed

def get_author_info(meta):
    author = meta.get('author_name', 'Unknown Author')
    dates = format_date(meta.get('date_filed'))
    if meta.get('date_blocked'):
        dates += f" | Blocked {format_date(meta['date_blocked'])}"
    return f"{author} | {dates}"

def get_opinion_type(opinion_code):
    types = {
        '010combined': 'Combined',
        '015unamimous': 'Unanimous',
        '015unaminous': 'Unanimous',
        '020lead': 'Lead',
        '025plurality': 'Plurality',
        '030concurrence': 'Concurrence',
        '035concurrenceinpart': 'Concurrence in Part',
        '040dissent': 'Dissent',
        '050addendum': 'Addendum',
        '060remittitur': 'Remittitur',
        '070rehearing': 'Rehearing',
        '080onthemerits': 'On the Merits',
        '090onmotiontostrike': 'On Motion to Strike'
    }
    return types.get(opinion_code, 'Unknown')

def truncate_text(text, max_length):
    return (text[:max_length] + '...') if len(text) > max_length else text

def get_file_icon(filename):
    extension = filename.split('.')[-1].lower()
    if extension == 'txt':
        return 'bi-file-text'
    elif extension in ['doc', 'docx']:
        return 'bi-file-word'
    elif extension == 'pdf':
        return 'bi-file-pdf'
    else:
        return 'bi-file-earmark'

def format_date(date_string):
    year, month, day = date_string.split('-')
    months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]
    return f"{months[int(month) - 1]} {int(day)}, {year}"

def organize_sources(new_sources):
    source_map = {}
    
    for new_source in new_sources:
        source_id = new_source['id']
        entity = new_source['entity']
        del new_source['entity']
        
        if source_id in source_map:
            # Check for existing entity with same PK
            existing_entities = source_map[source_id]['entities']
            if not any(e['pk'] == entity['pk'] for e in existing_entities):
                existing_entities.append(entity)
        else:
            source_map[source_id] = {
                'source': new_source,
                'entities': [entity],
                'original_index': len(source_map)  # Maintain insertion order
            }
    
    # Sort sources by original insertion order
    sorted_sources = sorted(source_map.values(), key=lambda x: x['original_index'])
    
    # Sort entities within each source by their PK
    for source_data in sorted_sources:
        source_data['entities'].sort(key=lambda x: x['pk'])
    
    return sorted_sources

@app.route('/search/<collection>', methods=['GET'])
def search(collection):
    start = time.time()
    if not collection:
        abort(404)
    semantic = request.args.get('semantic')
    if not semantic:
        return render_template("search.html", collection=collection, jurisdictions=JURISDICTIONS)
    keyword = request.args.get('keyword')
    jurisdictions = request.args.getlist('jurisdictions')
    after_date = request.args.get('after_date')
    before_date = request.args.get('before_date')
    data = {
        "collection": collection,
        "query": semantic,
        "k": 100
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
        generate_source_context(s['source'], i, s['entities'], keyword=keyword)
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

@app.route('/manage/<collection>', methods=['GET'])
def manage(collection):
    start = time.time()
    if not collection:
        abort(404)
    source = request.args.get("source")
    keyword = request.args.get("keyword")
    jurisdictions = request.args.getlist('jurisdictions')
    after_date = request.args.get('after_date')
    before_date = request.args.get('before_date')
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
        generate_source_context(s['source'], i, s['entities'], keyword=keyword)
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


@app.route('/create-agent', methods=['GET', 'POST'])
def create_agent():
    if request.method == 'POST':
        # Retrieve core fields
        system_prompt = request.form.get('system_prompt', '')
        message_prompt = request.form.get('message_prompt', '')
        num_search = int(request.form.get('num_search_tools', 1))
        num_vdb = int(request.form.get('num_vdb_tools', 0))
        
        # Build search tools list
        search_tools = []
        for i in range(num_search):
            tool = {
                "name": request.form.get(f"search_name_{i}", ""),
                "method": request.form.get(f"search_method_{i}", "dynamic_serpapi"),
                "prefix": request.form.get(f"search_prefix_{i}", ""),
                "prompt": request.form.get(f"search_prompt_{i}", "")
            }
            search_tools.append(tool)
        
        # Build VDB tools list
        vdb_tools = []
        for i in range(num_vdb):
            tool = {
                "name": request.form.get(f"vdb_name_{i}", ""),
                "collection_name": request.form.get(f"vdb_collection_{i}", ""),
                "k": request.form.get(f"vdb_k_{i}", 4),
                "prompt": request.form.get(f"vdb_prompt_{i}", "")
            }
            vdb_tools.append(tool)
        
        # Chat model configuration
        chat_model = {
            "engine": request.form.get("engine", "openai"),
            "model": request.form.get("model", "gpt-4o"),
            "temperature": request.form.get("temperature", 0),
            "seed": request.form.get("seed", 0)
        }
        
        bot_data = {
            "message_prompt": message_prompt,
            "search_tools": search_tools,
            "vdb_tools": vdb_tools,
            "chat_model": chat_model
        }

        if system_prompt:
            bot_data["system_prompt"] = system_prompt

        try:
            with api_request("create_bot", data=bot_data) as r:
                r.raise_for_status()
                result = r.json()
        except Exception:
            logger.exception("Create agent failed.")
            print(r.text)
            return jsonify({"error": "Failed to create agent."}), 400
        logger.debug("Created agent: %s", result)
        if result["message"] != "Success":
            logger.error("Create agent received an unexpected response.")
            flash("Failed to create agent.", "error")
            return redirect(url_for('create_agent'))
        if "bot_id" in result:
            flash(f"Agent created successfully! Agent ID: {result['bot_id']}", "success")
            flash(f"You can now chat with your agent at /agent/{result['bot_id']}", "info")
            return redirect(url_for('create_agent'))
        else:
            flash("Failed to create agent.", "error")
            return redirect(url_for('create_agent'))
    return render_template('create_agent.html')