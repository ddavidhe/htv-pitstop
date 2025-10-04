import os
from dotenv import load_dotenv          # NEW
load_dotenv()                            # NEW: load .env variables

import fitz                               # PyMuPDF
from flask import Flask, request, render_template, redirect, url_for
from openai import OpenAI

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from flask import session
import json

from tools import *

GOOGLE_CLIENT_SECRETS_FILE = "credentials.json"
SCOPES = ['https://www.googleapis.com/auth/calendar.events']


app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['UPLOAD_FOLDER'] = 'uploads'

# Retrieve API key from environment variables
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extract_text(pdf_path):
    text = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text.append(page.get_text())
    return "\n".join(text)

# @app.route("/", methods=["GET", "POST"])
# def index():
#     if request.method == "POST":
#         file = request.files["pdf"]
#         if file.filename == "":
#             return redirect(request.url)
#         save_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
#         file.save(save_path)

#         pdf_text = extract_text(save_path)

#         prompt = (
#             "Extract all assignment due dates and list weekly topics clearly "
#             "as JSON with fields: assignments.\n\n"
#             f"{pdf_text}"
#         )

#         response = client.chat.completions.create(
#             model="gpt-4.1",     # or "gpt-5"
#             messages=[
#                 {"role": "system", "content": "You are an assistant that extracts course details."},
#                 {"role": "user", "content": prompt}
#             ]
#         )
#         result = response.choices[0].message.content
#         session["last_pdf_json"] = result # store that in the session
#         return render_template("result.html", output=result)
#     return render_template("index.html")

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files["pdf"]
        if file.filename == "":
            return redirect(request.url)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(save_path)

        with open('sample.json', "r") as f:
            result = f.read()
        session["last_pdf_json"] = result # store that in the session
        return render_template("result.html", output=result)
    return render_template("index.html")       

@app.route("/authorize")
def authorize():
    flow = Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    session['state'] = state
    return redirect(authorization_url)

@app.route("/oauth2callback")
def oauth2callback():
    flow = Flow.from_client_secrets_file(
        GOOGLE_CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=session['state'],
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    flow.fetch_token(authorization_response=request.url)
    credentials = flow.credentials
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

    if session.get('redirect_after_auth') == 'sync_calendar':
        session.pop('redirect_after_auth', None)
        return redirect(url_for('sync_calendar'))

    return redirect(url_for('index'))


@app.route("/sync_calendar")
def sync_calendar():
    if 'credentials' not in session:
        session['redirect_after_auth'] = 'sync_calendar'
        return redirect(url_for('authorize'))
    print("Credentials found in session.")

    creds = Credentials(**session['credentials'])
    service = build('calendar', 'v3', credentials=creds)

    pdf_json = session.get("last_pdf_json")
    if not pdf_json:
        return "No PDF data to sync. Please upload a PDF first."
    
    output_json = json.loads(pdf_json)
    assignment_count = 0

    for a in output_json.get("assignments", []):
        iso_date = convert_date_to_iso(a.get("due_date", ""))
        event = {
            "summary": a.get("name", "Some Assignment"),
            "start": {"date": iso_date.strftime("%Y-%m-%d")},
            "end": {"date": iso_date.strftime("%Y-%m-%d")},
        }
        service.events().insert(calendarId='primary', body=event).execute()
        assignment_count += 1
    
    print(f"Inserted {assignment_count} assignments into calendar.")
    return render_template("success.html", count=assignment_count)


if __name__ == "__main__":
    os.makedirs("uploads", exist_ok=True)
    app.run(debug=True)
