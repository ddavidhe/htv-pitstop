import os
from dotenv import load_dotenv          # NEW
load_dotenv()                            # NEW: load .env variables

import fitz                               # PyMuPDF
from flask import Flask, request, render_template, redirect, url_for
from openai import OpenAI

app = Flask(__name__)
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
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(save_path)

        pdf_text = extract_text(save_path)

        prompt = (
            "Extract all assignment due dates and list weekly topics clearly "
            "as JSON with fields: assignments, labs, exams, weekly_topics.\n\n"
            f"{pdf_text}"
        )

        response = client.chat.completions.create(
            model="gpt-4.1",     # or "gpt-5"
            messages=[
                {"role": "system", "content": "You are an assistant that extracts course details."},
                {"role": "user", "content": prompt}
            ]
        )
        result = response.choices[0].message.content
        return render_template("result.html", output=result)
    return render_template("index.html")

if __name__ == "__main__":
    os.makedirs("uploads", exist_ok=True)
    app.run(debug=True)
