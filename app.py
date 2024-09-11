from flask import Flask, jsonify, request, render_template
import requests
import os
import re


app = Flask(__name__)

API_URL = os.environ["OPB_API_URL"]
API_KEY = os.environ["OPB_TEST_API_KEY"]
HEADERS = {"X-API-KEY": API_KEY}
BOT_ID = "courtlistener_bot"


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


@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template("index.html")

@app.route('/send', method="POST")
def send():
    if request.method == "POST":
        message = request.form["message"]
        data = {
            "botId": BOT_ID,
            "text": message,
            "userId": "test"
        }
        response = api_request("messages", method="POST", data=data)
        
        return jsonify(response), 200
    else:
        return jsonify({}), 405
