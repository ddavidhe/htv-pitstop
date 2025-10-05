import os
from dotenv import load_dotenv
load_dotenv()

import fitz
from flask import Flask, request, render_template, redirect, url_for
from openai import OpenAI

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from flask import session
import json

from tools import *
import time

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


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files["pdf"]
        if file.filename == "":
            return redirect(request.url)
        
        # Save the file and store in session for processing
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(save_path)
        session["uploaded_pdf_path"] = save_path
        
        # Show thinking screen while processing
        return render_template("thinking.html")
    
    return render_template("index.html")

# # # the fake route
# @app.route("/get_results")
# def get_results():
#     """This route actually processes the PDF and returns results"""
#     pdf_path = session.get("uploaded_pdf_path")
#     if not pdf_path:
#         return redirect(url_for('index'))
    
#     # For demo, use sample JSON (replace with real OpenAI call)
#     with open('cs241.json', "r") as f:
#         result = f.read()
#     session["last_pdf_json"] = result
#     time.sleep(5)
    
#     return render_template("result.html", output=result)

# Uncomment this when you want to use real OpenAI processing:
@app.route("/get_results")  
def get_results():
    pdf_path = session.get("uploaded_pdf_path")
    if not pdf_path:
        return redirect(url_for('index'))
    
    pdf_text = extract_text(pdf_path)
    
    prompt = (
        "Extract the course name, course code, all assignment names with due dates, "
        "and weekly topics clearly as JSON with fields: course_name, course_code, assignments, weekly_topics.\n\n"
        "for assignments, you MUST only have 2 things per entry, name and due_date. Ensure that the due_date field is in form of Sep 29 or Nov 25 where month is the first 3 letters of the month.\n\n"
        "for weekly topics, you MUST have 2 things per entry. range (with dates in the form of Jun 15 or Feb 11) and topics, which will be 1 string with SEMICOLONs ; to deliminate. if multiple dates exist in the range, seperate via dash like Oct 20 - Oct 25.\n\n"
        "you do NOT need to include the final exam or the midterm if there is no date listed.\n\n"
        f"{pdf_text}"
    )

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are an assistant that extracts course details."},
            {"role": "user", "content": prompt}
        ]
    )
    result = response.choices[0].message.content
    session["last_pdf_json"] = result
    return render_template("result.html", output=result)


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

    redirect_route = session.get('redirect_after_auth')
    if redirect_route == 'sync_calendar':
        session.pop('redirect_after_auth', None)
        return redirect(url_for('sync_calendar'))
    elif redirect_route == 'sync_calendar_time':
        session.pop('redirect_after_auth', None)
        return redirect(url_for('sync_calendar_time'))
    else:
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
    calendar_name = 'PitStop Assignments'
    try:
        calendar_list = service.calendarList().list().execute()
        for calendar in calendar_list.get('items', []):
            if calendar.get('summary') == calendar_name:
                calendar_id = calendar.get('id')
                print(f"Found existing calendar with ID: {calendar_id}")
                break
    except Exception as e:
        print(f"Error fetching calendar list: {e}")

    if not calendar_id:
        # create new calendar
        output_json = json.loads(pdf_json)
        course_code = output_json.get("course_code", "PitStop Assignments")
        
        calendar_body = {
            'summary': f'{course_code} - PitStop Assignments',
            'description': 'Assignments imported from PitStop',
            'timeZone': 'America/Los_Angeles'
        }
        calendar_name = f'{course_code} - PitStop'

        try:
            created_calendar = service.calendars().insert(body=calendar_body).execute()
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
    return render_template("success.html", count=assignment_count, type="assignments")

@app.route("/swipe_topics")
def swipe_topics():
    pdf_json = session.get("last_pdf_json")
    
    if pdf_json:
        output_json = json.loads(pdf_json)
        topics = []

        for week_date in output_json.get("weekly_topics", []):
            if isinstance(week_date, dict):
                topic = week_date.get("topics", "No Topic")
                week_topics = [topic.strip() for topic in topic.split(";")]
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

    # Map ratings to numerical values
    rating_map = {'soso': 0.5, 'familiar': 1, 'weak': 0}
    mapped_swipe_data = [{'topic': item['topic'], 'rating': rating_map.get(item['rating'], 0)} for item in swipe_data]

    print("Mapped swipe data: ", mapped_swipe_data)

    session["swipe_data"] = swipe_data
    return {"status": "success"}

# # # This route is the sample one.
# @app.route("/timeblock")
# def timeblock():
#     pdf_json = session.get("last_pdf_json")
#     swipe_results = session.get("swipe_data", [])

#     if not pdf_json or not swipe_results:
#         return redirect(url_for('index'))
    
#     try:
#         with open('sample_times.json', "r") as f:
#             study_schedule = json.load(f)  # ← Load as JSON object
#         session["study_schedule"] = json.dumps(study_schedule)
    
#         return render_template("result_time.html", schedule=study_schedule)  # ← Pass as object

#     except Exception as e:
#         print(f"Error loading study schedule: {e}")
#         return render_template("index.html", message="Failed to load study schedule.")
    
@app.route("/timeblock")
def timeblock():
    output_json = session.get("last_pdf_json")
    output_json = json.loads(output_json) if output_json else None
    topics_rating = session.get("swipe_data", [])

    if not output_json or not topics_rating:
        return redirect(url_for('index'))
    
    prompt = (
        
        "Based on this assignment data and a student's self-assessment ratings, create an optimal study schedule.\n\n"
        "ASSIGNMENTS:\n\n"
        f"{json.dumps(output_json.get('assignments', []), indent=2)}\n\n"
        "STUDENT RATINGS:\n\n"
        f"{json.dumps(topics_rating, indent=2)}\n\n"
        "GUIDELINES:\n"
        "Only scheudle study sessions between 9AM and 9PM.\n\n"
        "Schedule at most 3 hours for weekdays (mon-fri) and 5 hours for weekends (sat-sun).\n\n"
        "Prioritze topics with lower ratings (0 = weak, 0.5 = soso, 1 = familiar). Allocate most time for 0 and some time for 0.5, it's ok to not have any time for things ranked 1.\n\n"
        "Distribute study sessions according to incoming due dates. Schedule greedily\n\n"
        "Schedule topics BEFORE their weekly_topics dates, and spread sessions across multiple days for more retention.\n\n"
        "In general try to give topics with 0 about 3 hours a week, and 0.5 about 2 hours a week.\n\n"
        "Return a JSON with this structure and NO OTHER TEXT:\n"
        """{
            "study_sessions": [
                {
                    "date": "YYYY-MM-DD",
                    "start_time": "HH:MM",
                    "end_time": "HH:MM",
                    "topics": ["Topic 1", "Topic 2"]
                }
            ]
            }
        """
        "Follow this JSON format religiously, do not add any extra text outside the JSON. Ensure dates and times are in the correct format.\n\n"
    )

    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are an assistant that creates study schedules."},
            {"role": "user", "content": prompt}
        ]
    )
    result = response.choices[0].message.content
    print("Study Schedule JSON: ", result)

    try:
        study_schedule = json.loads(result)  # ← Load as JSON object
        session["study_schedule"] = json.dumps(study_schedule)
    
        return render_template("result_time.html", schedule=study_schedule)  # ← Pass as object

    except Exception as e:
        print(f"Error parsing study schedule: {e}")
        return render_template("index.html", message="Failed to parse study schedule.")


@app.route("/sync_calendar_time")
def sync_calendar_time():
    if 'credentials' not in session:
        session['redirect_after_auth'] = 'sync_calendar_time'
        return redirect(url_for('authorize'))
    
    creds = Credentials(**session['credentials'])
    service = build('calendar', 'v3', credentials=creds)

    # Get study schedule from session
    study_schedule_json = session.get("study_schedule")
    if not study_schedule_json:
        return "No study schedule to sync. Please generate a timeblock schedule first."
    
    # Parse the schedule (it's stored as JSON string)
    study_schedule = json.loads(study_schedule_json)

    # Find or create the same calendar as assignments
    calendar_id = None
    calendar_name = 'PitStop Assignments'
    
    try:
        calendar_list = service.calendarList().list().execute()
        for calendar in calendar_list.get('items', []):
            if calendar_name in calendar.get('summary', ''):
                calendar_id = calendar.get('id')
                print(f"Found existing calendar with ID: {calendar_id}")
                break
    except Exception as e:
        print(f"Error fetching calendar list: {e}")
    
    if not calendar_id:
        # Create calendar if it doesn't exist
        pdf_json = session.get("last_pdf_json")
        if pdf_json:
            output_json = json.loads(pdf_json)
            course_code = output_json.get("course_code", "PitStop")
        else:
            course_code = "PitStop"
        
        calendar_body = {
            'summary': f'{course_code} - PitStop Assignments',
            'description': 'Study schedule and assignments from PitStop',
            'timeZone': 'America/Los_Angeles'
        }

        try:
            created_calendar = service.calendars().insert(body=calendar_body).execute()
            calendar_id = created_calendar['id']
            print(f"Created new calendar with ID: {calendar_id}")
        except Exception as e:
            print(f"Error creating calendar: {e}")
            return "Failed to create calendar."

    # Add study sessions to calendar
    session_count = 0
    
    for study_session in study_schedule.get("study_sessions", []):
        start_datetime = f"{study_session['date']}T{study_session['start_time']}:00"
        end_datetime = f"{study_session['date']}T{study_session['end_time']}:00"
        topics_str = ", ".join(study_session.get("topics", []))

        event = {
            "summary": f"Study: {topics_str}",
            "description": f"PitStop study session for: {topics_str}",
            "start": {"dateTime": start_datetime, "timeZone": "America/Los_Angeles"},
            "end": {"dateTime": end_datetime, "timeZone": "America/Los_Angeles"},
        }
        
        try: 
            service.events().insert(calendarId=calendar_id, body=event).execute()
            session_count += 1
            print(f"Added study session: {topics_str} on {study_session['date']}")
        except Exception as e:
            print(f"Error inserting study session: {e}")
    
    print(f"Inserted {session_count} study sessions into calendar.")
    return render_template("success.html", count=session_count, type="study sessions")

if __name__ == "__main__":
    os.makedirs("uploads", exist_ok=True)
    app.run(debug=True)
