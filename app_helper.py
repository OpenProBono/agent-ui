import datetime
import logging
import os
import re
from html import escape

import requests
from markdown import markdown

JURISDICTIONS = [
    {"display": "Federal Appellate", "value": "us-app"},
    {"display": "Federal District", "value": "us-dis"},
    {"display": "Federal Supreme Court", "value": "us-sup"},
    {"display": "Federal Special", "value": "us-misc"},
    {"display": "Alabama", "value": "al"},
    {"display": "Alaska", "value": "ak"},
    {"display": "Arizona", "value": "az"},
    {"display": "Arkansas", "value": "ar"},
    {"display": "California", "value": "ca"},
    {"display": "Colorado", "value": "co"},
    {"display": "Connecticut", "value": "ct"},
    {"display": "Delaware", "value": "de"},
    {"display": "District of Columbia", "value": "dc"},
    {"display": "Florida", "value": "fl"},
    {"display": "Georgia", "value": "ga"},
    {"display": "Hawaii", "value": "hi"},
    {"display": "Idaho", "value": "id"},
    {"display": "Illinois", "value": "il"},
    {"display": "Indiana", "value": "in"},
    {"display": "Iowa", "value": "ia"},
    {"display": "Kansas", "value": "ks"},
    {"display": "Kentucky", "value": "ky"},
    {"display": "Louisiana", "value": "la"},
    {"display": "Maine", "value": "me"},
    {"display": "Maryland", "value": "md"},
    {"display": "Massachusetts", "value": "ma"},
    {"display": "Michigan", "value": "mi"},
    {"display": "Minnesota", "value": "mn"},
    {"display": "Mississippi", "value": "ms"},
    {"display": "Missouri", "value": "mo"},
    {"display": "Montana", "value": "mt"},
    {"display": "Nebraska", "value": "ne"},
    {"display": "Nevada", "value": "nv"},
    {"display": "New Hampshire", "value": "nh"},
    {"display": "New Jersey", "value": "nj"},
    {"display": "New Mexico", "value": "nm"},
    {"display": "New York", "value": "ny"},
    {"display": "North Carolina", "value": "nc"},
    {"display": "North Dakota", "value": "nd"},
    {"display": "Ohio", "value": "oh"},
    {"display": "Oklahoma", "value": "ok"},
    {"display": "Oregon", "value": "or"},
    {"display": "Pennsylvania", "value": "pa"},
    {"display": "Rhode Island", "value": "ri"},
    {"display": "South Carolina", "value": "sc"},
    {"display": "South Dakota", "value": "sd"},
    {"display": "Tennessee", "value": "tn"},
    {"display": "Texas", "value": "tx"},
    {"display": "Utah", "value": "ut"},
    {"display": "Vermont", "value": "vt"},
    {"display": "Virginia", "value": "va"},
    {"display": "Washington", "value": "wa"},
    {"display": "West Virginia", "value": "wv"},
    {"display": "Wisconsin", "value": "wi"},
    {"display": "Wyoming", "value": "wy"},
]


formatter = logging.Formatter("%(asctime)s %(levelname)s %(funcName)s %(message)s")
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("logger")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

api_url = "http://0.0.0.0:8080" #os.environ["OPB_API_URL"]

def api_request(
    endpoint,
    method="POST",
    id_token=None,
    data=None,
    files=None,
    params=None,
    timeout=None,
    stream=None,
) -> requests.Response:
    headers = {}
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"
    url = f"{api_url}/{endpoint}"
    logger.info("Making %s request to /%s", method, endpoint)
    if method == "GET":
        return requests.get(url, headers=headers, params=data, timeout=timeout, stream=stream)
    elif method == "DELETE":
        return requests.delete(url, headers=headers, json=data, timeout=timeout, stream=stream)
    return requests.post(url, headers=headers, json=data, files=files, params=params, timeout=timeout, stream=stream)


def mark_keyword(text, keyword):
    # Split the keyword into individual words
    keywords = keyword.split()

    # Create a pattern to match the full keyword phrase first
    phrases_pattern = r"\b" + re.escape(keyword) + r"\b"
    phrases_compiled = re.compile(phrases_pattern, re.IGNORECASE)

    def replace_func(match):
        return f"<mark>{match.group()}</mark>"

    # First, mark the full keyword phrase
    text = phrases_compiled.sub(replace_func, text)

    # Create a pattern to match individual words only if they are standalone
    words_pattern = r"\b" + r"\b|\b".join(re.escape(word) for word in keywords) + r"\b"
    words_compiled = re.compile(words_pattern, re.IGNORECASE)

    # Mark individual words only if the full phrase is not marked
    return words_compiled.sub(
        lambda match: match.group()
        if f"<mark>{match.group()}</mark>" in text
        else replace_func(match), text,
    )


def format_summary(summary):
    # Split the summary into lines
    lines = summary.split("\n")

    # Process each line
    formatted_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Check if the line contains a title (wrapped in asterisks)
        title_match = re.search(r"\*\*(.*?)\*\*", line)
        if title_match:
            # Extract the title
            title = title_match.group(1)
            # Replace the entire **title** part with HTML strong tags
            line = re.sub(r"\*\*.*?\*\*", f"<strong>{title}</strong>", line)
            # Remove leading dash if present
            line = re.sub(r"^- ?", "", line)

        formatted_lines.append(line)

    # Join the lines with line breaks
    return "<br>".join(formatted_lines)


def generate_source_context(source, index, entities, keyword=None):
    source_type = source["type"]
    context = {
        "index": index + 1,
        "type": source_type,
        "entities": process_entities(entities, keyword=keyword),
        "num_entities": len(entities),
    }
    meta = entities[0]["metadata"]
    if source_type == "opinion":
        context.update({
            "case_name": truncate_text(meta.get("case_name", ""), 150),
            "court_name": meta.get("court_name", ""),
            "url": f"https://www.courtlistener.com/opinion/{meta.get('cluster_id', '')}/{meta.get('slug', '')}",
            "author_info": get_author_info(meta),
            "opinion_type": get_opinion_type(meta.get("type", "")),
            "download_url": meta.get("download_url"),
            "courtlistener_summary": meta.get("summary"),
            "ai_summary": markdown(meta.get("ai_summary", "")) if meta.get("ai_summary") else None,
            "other_dates": meta.get("other_dates")
        })
    elif source_type == "url":
        context.update({
            "url": source["id"],
            "source": meta.get("source", source["id"]),
            "title": meta.get("title", "Title Not Found"),
            "ai_summary": markdown(meta.get("ai_summary", "")) if meta.get("ai_summary") else None,
        })
        epoch_time = meta.get("timestamp", None)
        if epoch_time:
            date_object = datetime.datetime.fromtimestamp(float(meta.get("timestamp")), tz=datetime.UTC)
            formatted_date = date_object.strftime("%Y-%m-%d")
            context["timestamp"] = format_date(formatted_date)
    elif source_type == "file":
        context.update({
            "filename": source["id"],
            "file_icon": get_file_icon(source["id"])
        })
        epoch_time = meta.get("timestamp", None)
        if epoch_time:
            date_object = datetime.datetime.fromtimestamp(meta.get("timestamp"), tz=datetime.UTC)
            formatted_date = date_object.strftime("%Y-%m-%d")
            context["timestamp"] = format_date(formatted_date)
    return context


def process_entities(entities, keyword=None):
    processed = []
    for entity in entities:
        text = escape(entity["text"])
        if keyword:
            text = mark_keyword(text, keyword)
        text = text.replace("\n", "<br>")
        processed_entity = {"text": text}
        if "distance" in entity:
            processed_entity["match_score"] = round(max([0, (2 - entity["distance"]) / 2]), 8)
        if "page_number" in entity["metadata"]:
            processed_entity["page_number"] = entity["metadata"]["page_number"]
        processed.append(processed_entity)
    return processed


def get_author_info(meta):
    author = meta.get("author_name", "Unknown Author")
    dates = format_date(meta.get("date_filed"))
    if meta.get("date_blocked"):
        dates += f" | Blocked {format_date(meta['date_blocked'])}"
    return f"{author} | {dates}"


def get_opinion_type(opinion_code):
    types = {
        "010combined": "Combined",
        "015unamimous": "Unanimous",
        "015unaminous": "Unanimous",
        "020lead": "Lead",
        "025plurality": "Plurality",
        "030concurrence": "Concurrence",
        "035concurrenceinpart": "Concurrence in Part",
        "040dissent": "Dissent",
        "050addendum": "Addendum",
        "060remittitur": "Remittitur",
        "070rehearing": "Rehearing",
        "080onthemerits": "On the Merits",
        "090onmotiontostrike": "On Motion to Strike",
    }
    return types.get(opinion_code, "Unknown")


def truncate_text(text, max_length):
    return (text[:max_length] + "...") if len(text) > max_length else text


def get_file_icon(filename):
    extension = filename.split(".")[-1].lower()
    if extension == "txt":
        return "bi-file-text"
    if extension in ["doc", "docx"]:
        return "bi-file-word"
    if extension == "pdf":
        return "bi-file-pdf"
    return "bi-file-earmark"


def format_date(date_string):
    year, month, day = date_string.split("-")
    months = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    return f"{months[int(month) - 1]} {int(day)}, {year}"


def organize_sources(new_sources):
    source_map = {}

    for new_source in new_sources:
        source_id = new_source["id"]
        entity = new_source["entity"]
        del new_source["entity"]

        if source_id in source_map:
            # Check for existing entity with same PK
            existing_entities = source_map[source_id]["entities"]
            if not any(e["pk"] == entity["pk"] for e in existing_entities):
                existing_entities.append(entity)
        else:
            source_map[source_id] = {
                "source": new_source,
                "entities": [entity],
                "original_index": len(source_map),  # Maintain insertion order
            }

    # Sort sources by original insertion order
    sorted_sources = sorted(source_map.values(), key=lambda x: x["original_index"])

    # Sort entities within each source by their PK
    for source_data in sorted_sources:
        source_data["entities"].sort(key=lambda x: x["pk"])

    return sorted_sources
