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
SCOPES = ['https://www.googleapis.com/auth/calendar.events',
          'https://www.googleapis.com/auth/calendar']


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

# the real route that uses openai lol
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
#             "Extract the course name, course code, all assignment names with due dates, "
#             "and weekly topics clearly as JSON with fields: course_name, course_code, assignments, weekly_topics.\n\n"
#             "for assignments, ensure that the due_date field is in form of Sep 29 or Nov 25 where month is the first 3 letters of the month.\n\n"
#             "for weekly topics, keep the ranges.\n\n"
#             "you do NOT need to include the final exam or the midterm if there is nore date listed.\n\n"
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

# PURELY FOR THE SAMPLE, USES THE JSON THAT ALREADY EXISTS TO COP OUT OF OPENAI COSTS
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files["pdf"]
        if file.filename == "":
            return redirect(request.url)
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(save_path)

        with open('sample2.json', "r") as f:
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
    
    # check to see if it exists yet
    calendar_id = None
    calender_name = 'PitStop Assignments'
    try:
        calendar_list = service.calendarList().list().execute()
        for calendar in calendar_list.get('items', []):
            if calendar.get('summary') == calender_name:
                calendar_id = calendar.get('id')
                print(f"Found existing calendar with ID: {calendar_id}")
                break
    except Exception as e:
        print(f"Error fetching calendar list: {e}")

    if not calendar_id:
        # create new calendar
        calender_body = {
            'summary': 'PitStop Assignments',
            'description': 'Assignments imported from PitStop',
            'timeZone': 'America/Los_Angeles'
        }

        try:
            created_calendar = service.calendars().insert(body=calender_body).execute()
            calendar_id = created_calendar['id']
            print(f"Created new calendar with ID: {calendar_id}")
        except Exception as e:
            print(f"Error creating calendar: {e}")
            return "Failed to create calendar."
    
    # populate
    output_json = json.loads(pdf_json)
    assignment_count = 0

    for a in output_json.get("assignments", []):
        iso_date = convert_date_to_iso(a.get("due_date", ""))
        event = {
            "summary": a.get("name", "Some Assignment"),
            "start": {"date": iso_date.strftime("%Y-%m-%d")},
            "end": {"date": iso_date.strftime("%Y-%m-%d")},
        }
        service.events().insert(calendarId=calendar_id, body=event).execute()
        assignment_count += 1
    
    print(f"Inserted {assignment_count} assignments into calendar.")
    return render_template("success.html", count=assignment_count)

@app.route("/swipe_topics")
def swipe_topics():
    pdf_json = session.get("last_pdf_json")
    
    if pdf_json:
        output_json = json.loads(pdf_json)
        topics = []

        for week_date in output_json.get("weekly_topics", []):
            if isinstance(week_date, dict):
                topic = week_date.get("topics", "No Topic")
                week_topics = [topic.strip() for topic in topic.split(",")]
                topics.extend(week_topics)
            else:
                topics.append(str(week_date))

        topics = [topic for topic in topics if topic] # remove empty
        topics = list(set(topics))  # Remove duplicate topics
    else:
        topics = ["Topic 1", "Topic 2", "Topic 3"]  # Fallback topics

    return render_template("swipe.html", topics=topics)

@app.route("/swipe_result", methods=["POST"])
def swipe_result():
    swipe_data = request.get_json()
    print("Swipe result: ", swipe_data)
    # TODO: sqlite
    return {"status": "success"}


@app.route("/time_block")
def time_block():
    return render_template("timeblock.html")


if __name__ == "__main__":
    os.makedirs("uploads", exist_ok=True)
    app.run(debug=True)
