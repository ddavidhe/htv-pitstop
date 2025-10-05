# PitStop
Gearing up for the new semester? PitStop helps you and your calendar fuel up to tackle the upcoming term properly. PitStop uses your course syllabus and other contexts to agentically block time out of your calender for non-conflicting deep work periods. With secure OAuth2.0 verification, Google Cloud Platform integration, and OpenAI processing power, PitStop takes your existing courses, upcoming assignments, and your personal familiarity to course concepts all into consideration when executing its task. 

## Try PitStop

Clone the repository

Enter the root directory and create + activate a `.venv` instance
```bash
python -m venv .venv
source .venv/bin/activate
```

Copy the `.env_example`, rename it to be `.env`, and attach your OpenAI key from https://platform.openai.com/api-keys

Create a new Google Cloud Platform project from https://console.cloud.google.com/welcome and navigate through the sidebar:
```bash
APIs & Services > Enabled APIs & services 
```
Enable the Google Calender API. Copy your `credentials.json` file and paste it into the root directory.

Install all dependancies
```bash
pip install -r requirements.txt
```

Finally,
```bash
python3 app.py
```
