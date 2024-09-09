from flask import Flask, jsonify, request, render_template
import requests
from datetime import datetime
import os
import re
import time


app = Flask(__name__)

COURTLISTENER = "https://www.courtlistener.com"
API_URL = os.environ["OPB_API_URL"]
CASE_ENDPOINT = API_URL + "/search_opinions"
SUMMARY_ENDPOINT = API_URL + "/get_opinion_summary"
COUNT_ENDPOINT = API_URL + "/get_opinion_count"
FEEDBACK_ENDPOINT = API_URL + "/opinion_feedback"
API_KEY = os.environ["OPB_TEST_API_KEY"]
HEADERS = {"X-API-KEY": API_KEY}
ERROR_MSG = "Error searching for opinions. Please try again later."

class Opinion:

    def __init__(
        self, opinion_id: int, case_name: str, court_name: str, author_name: str, ai_summary: str,
        text: str, date_filed: str, url: str, date_blocked: str, other_dates: str, summary: str,
        download_url: str, match_score: float
    ) -> None:
        self.opinion_id = opinion_id
        self.case_name = case_name
        self.court_name = court_name
        self.author_name = author_name
        self.ai_summary = ai_summary
        self.text = text
        self.date_filed = date_filed
        self.url = url
        self.date_blocked = date_blocked
        self.other_dates = other_dates
        self.summary = summary
        self.download_url = download_url
        self.match_score = match_score

def api_request(endpoint, method="POST", data=None, files=None, params=None):
    url = f"{API_URL}/{endpoint}"
    if method == "GET":
        response = requests.get(url, headers=HEADERS, params=data)
    else:
        response = requests.post(url, headers=HEADERS, json=data, files=files, params=params)
    
    return response.json()


def api_request_stream(endpoint, data=None):
    url = f"{API_URL}/{endpoint}"
    response = requests.post(url, headers=HEADERS, json=data, stream=True)
    return response

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
    formatted_content = '<br>'.join(formatted_lines)
    
    # Wrap everything in a single paragraph tag
    return f'<p>{formatted_content}</p>'

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        response = requests.post(CASE_ENDPOINT, headers=HEADERS, json=params, timeout=90)
        if response.status_code == 200:
            response_json = response.json()
            if "results" not in response_json:
                return ERROR_MSG
            opinions = response_json["results"]
            # get results_opinion_count
            opinion_ids = set()
            for opinion in opinions:
                if opinion["entity"]["metadata"]["id"] not in opinion_ids:
                    opinion_ids.add(opinion["entity"]["metadata"]["id"])
            results_opinion_count = len(opinion_ids)
            # format opinions
            formatted_opinions = []
            for opinion in opinions:
                match_score = round(max([0, (2 - opinion['distance']) / 2]), 8)
                metadata = opinion["entity"]["metadata"]
                case_name = metadata["case_name"]
                if len(case_name) > 200:
                    case_name = case_name[:200] + "..."
                court_name = metadata["court_name"]
                author_name = metadata["author_name"] if "author_name" in metadata else None
                ai_summary = format_summary(metadata["ai_summary"]) if "ai_summary" in metadata else None
                # CL summary
                summary = metadata["summary"] if "summary" in metadata else None
                download_url = metadata["download_url"] if "download_url" in metadata else None
                # matched excerpt
                text = format_str(opinion["entity"]["text"])
                text = f"""<p>{text}</p>"""
                if keyword:
                    text = mark_keyword(text, keyword)
                # full text link
                if "slug" in metadata:
                    url = COURTLISTENER + f"/opinion/{metadata['cluster_id']}/{metadata['slug']}/"
                elif "absolute_url" in metadata:
                    url = COURTLISTENER + metadata["absolute_url"]
                else:
                    url = None
                # dates
                date_filed = datetime.strptime(metadata["date_filed"], "%Y-%m-%d").strftime("%B %d, %Y")
                other_dates = metadata["other_dates"] if "other_dates" in metadata else None
                if "date_blocked" in metadata:
                    date_blocked = datetime.strptime(metadata["date_blocked"], "%Y-%m-%d").strftime("%B %d, %Y")
                else:
                    date_blocked = None
                formatted_opinions.append(Opinion(**{
                    "opinion_id": metadata["id"],
                    "case_name": case_name,
                    "court_name": court_name,
                    "author_name": author_name,
                    "ai_summary": ai_summary,
                    "text": text,
                    "date_filed": date_filed,
                    "url": url,
                    "download_url": download_url,
                    "date_blocked": date_blocked,
                    "other_dates": other_dates,
                    "summary": summary,
                    "match_score": match_score,
                }))
            end = time.time()
            elapsed = str(round(end - start, 5))
            return render_template(
                "index.html",
                results=formatted_opinions,
                form_data=params,
                jurisdictions=JURISDICTIONS,
                results_opinion_count=results_opinion_count,
                elapsed=elapsed,
            )
        else:
            return ERROR_MSG
    return render_template("index.html", jurisdictions=JURISDICTIONS)

