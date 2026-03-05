import os
import json
import requests
import time
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from google import genai
from google.genai import types
from supabase import create_client, Client

load_dotenv()

app = Flask(__name__)

# --- SUPABASE CLIENT ---
supabase: Client = create_client(
    os.environ.get("SUPABASE_URL"),
    os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY")
)

# --- CACHE ---
latest_ai_prediction = None
last_ai_update_time = 0
latest_live_score = None
last_live_score_time = 0

# --- SQUAD LISTS ---
SQUADS = {
    "India": [
        "Suryakumar Yadav", "Sanju Samson", "Axar Patel", "Kuldeep Yadav", "Hardik Pandya",
        "Jasprit Bumrah", "Ishan Kishan", "Rinku Singh", "Mohammed Siraj", "Washington Sundar",
        "Shivam Dube", "Abhishek Sharma", "Varun Chakaravarthy", "Arshdeep Singh", "Tilak Varma"
    ],
    "England": [
        "Liam Dawson", "Adil Rashid", "Jos Buttler", "Jamie Overton", "Ben Duckett",
        "Jofra Archer", "Luke Wood", "Sam Curran", "Phil Salt", "Josh Tongue",
        "Harry Brook", "Tom Banton", "Will Jacks", "Jacob Bethell", "Rehan Ahmed"
    ]
}

# --- CRICAPI INTEGRATION ---
def get_mock_match():
    return {
        "name": "India vs England, Semi-Final",
        "matchType": "t20",
        "status": "Match yet to begin",
        "venue": "Kensington Oval, Bridgetown",
        "teams": ["India", "England"],
        "score": []
    }

def get_live_score():
    api_key = os.environ.get("CRICAPI_KEY")
    url = f"https://api.cricapi.com/v1/currentMatches?apikey={api_key}&offset=0"
    try:
        res = requests.get(url).json()
        if res.get("status") == "success":
            for match in res.get("data", []):
                teams = match.get("teams", [])
                if "India" in teams and "England" in teams:
                    return match
    except Exception as e:
        print(f"CricAPI Error: {e}")

    return get_mock_match()

# --- GEMINI AI INTEGRATION ---
def generate_ai_prediction(live_data):
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    context = json.dumps(live_data)
    model = "gemini-3.1-pro-preview"

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=f"Live Match Context: {context}\n\nBased on historical records, current live scores, and T20 dynamics for India vs England, predict the final stats. Return a JSON structure ONLY with keys: 'ind_win_prob' (int), 'eng_win_prob' (int), 'ind_projected_score' (int), 'eng_projected_score' (int)."),
            ],
        ),
    ]

    generate_content_config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=genai.types.Schema(
            type=genai.types.Type.OBJECT,
            properties={
                "response": genai.types.Schema(
                    type=genai.types.Type.STRING,
                ),
            },
        ),
        system_instruction=[
            types.Part.from_text(text="You are an expert cricket analyst AI. Provide accurate predictions in valid JSON format inside the response string."),
        ],
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )

        outer_json = json.loads(response.text)
        inner_string = outer_json.get("response", "{}")
        inner_string = inner_string.replace('```json', '').replace('```', '').strip()

        return json.loads(inner_string)
    except Exception as e:
        print(f"Gemini AI Error: {e}")
        return {
            "ind_win_prob": 55, "eng_win_prob": 45,
            "ind_projected_score": 195, "eng_projected_score": 185
        }

@app.route("/")
def index():
    return render_template("index.html", squads=SQUADS)

@app.route("/api/live_match")
def live_match():
    global latest_live_score, last_live_score_time
    current_time = time.time()
    if not latest_live_score or (current_time - last_live_score_time) > 60:
        latest_live_score = get_live_score()
        last_live_score_time = current_time
    return jsonify(latest_live_score)

@app.route("/api/ai_predictions")
def ai_predictions():
    global latest_ai_prediction, last_ai_update_time
    current_time = time.time()

    if not latest_ai_prediction or (current_time - last_ai_update_time) > 300:
        live_data = get_live_score()
        latest_ai_prediction = generate_ai_prediction(live_data)
        last_ai_update_time = current_time

    return jsonify(latest_ai_prediction)

@app.route("/api/predict", methods=["POST"])
def submit_prediction():
    data = request.json
    username = data.get("username", "").strip()
    if not username:
        return jsonify({"error": "Username required"}), 400

    # Check if this user has already submitted a prediction
    existing = supabase.table("predictions").select("username").eq("username", username).execute()
    if existing.data:
        return jsonify({"error": "You have already submitted a prediction. Updates are not allowed."}), 409

    supabase.table("predictions").insert({
        "username": username,
        "winner": data.get("winner"),
        "motm": data.get("motm"),
        "most_runs": data.get("most_runs"),
        "most_wickets": data.get("most_wickets"),
        "most_catches": data.get("most_catches")
    }).execute()

    return jsonify({"message": "Prediction saved successfully!"})

@app.route("/api/leaderboard")
def leaderboard():
    rows = supabase.table("predictions").select("*").execute().data

    user_predictions = {row["username"]: {
        "winner": row["winner"],
        "motm": row["motm"],
        "most_runs": row["most_runs"],
        "most_wickets": row["most_wickets"],
        "most_catches": row["most_catches"]
    } for row in rows}

    stats = {
        "winner": {}, "motm": {}, "most_runs": {}, "most_wickets": {}, "most_catches": {}
    }

    for user, preds in user_predictions.items():
        for category, selection in preds.items():
            if selection:
                if selection not in stats[category]:
                    stats[category][selection] = {"count": 0, "voters": []}
                stats[category][selection]["count"] += 1
                stats[category][selection]["voters"].append(user)

    return jsonify({
        "predictions": user_predictions,
        "statistics": stats
    })

if __name__ == "__main__":
    app.run(debug=True, port=5001)
