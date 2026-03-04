import os
import json
import time
import requests
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

app = Flask(__name__)

# Global variables to handle friends' predictions and AI caching
user_predictions = []
ai_cache = {
    "timestamp": 0,
    "data": None
}

CRICAPI_KEY = os.environ.get("CRICAPI_KEY")

def get_live_match_data():
    """Fetches real data from CricAPI. Falls back to mock data if IND vs ENG is not live yet."""
    try:
        url = f"https://api.cricapi.com/v1/currentMatches?apikey={CRICAPI_KEY}&offset=0"
        response = requests.get(url).json()
        
        # Search for India vs England match
        if response.get("status") == "success":
            for match in response.get("data", []):
                teams = match.get("teams", [])
                if "India" in teams and "England" in teams:
                    return match
    except Exception as e:
        print("Error fetching real match data:", e)

    # MOCK DATA: Used to test the app before the match actually starts
    return {
        "name": "India vs England, Semi-Final - T20 World Cup",
        "matchType": "t20",
        "status": "India won the toss and elected to bat",
        "venue": "World Cup Stadium",
        "teams": ["India", "England"],
        "score": [
            {"inning": "India Inning 1", "r": 168, "w": 3, "o": 15.4}
        ],
        "isMock": True
    }

def generate_ai_predictions(match_data):
    """Calls Gemini API with the context to make live predictions"""
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
    )

    model = "gemini-3.1-pro-preview"
    
    # Passing context to the AI
    prompt_text = f"""
    You are an expert cricket AI analyst. Look at this live/mock data for India vs England T20 match:
    {json.dumps(match_data)}
    
    Take into account historical context, T20 World Cup pressure, pitch conditions, and current momentum.
    Make highly accurate numerical predictions for the final outcome.
    """

    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt_text)],
        ),
    ]
    
    # Configured exactly as requested, but schema expanded for charts
    generate_content_config = types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(
            thinking_level="HIGH",
        ),
        response_mime_type="application/json",
        response_schema=genai.types.Schema(
            type=genai.types.Type.OBJECT,
            properties={
                "win_probability_india": genai.types.Schema(type=genai.types.Type.INTEGER),
                "win_probability_england": genai.types.Schema(type=genai.types.Type.INTEGER),
                "projected_score_india": genai.types.Schema(type=genai.types.Type.INTEGER),
                "projected_score_england": genai.types.Schema(type=genai.types.Type.INTEGER),
                "total_sixes_predicted": genai.types.Schema(type=genai.types.Type.INTEGER),
                "analysis_summary": genai.types.Schema(type=genai.types.Type.STRING),
            },
        ),
        system_instruction=[
            types.Part.from_text(text="You are an expert T20 Cricket Analyst. Always return valid JSON matching the schema."),
        ],
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=generate_content_config,
        )
        return json.loads(response.text)
    except Exception as e:
        print("Gemini API Error:", e)
        return {
            "win_probability_india": 55, "win_probability_england": 45,
            "projected_score_india": 190, "projected_score_england": 180,
            "total_sixes_predicted": 14, "analysis_summary": "API Error: Using fallback predictions."
        }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/match-data')
def api_match_data():
    data = get_live_match_data()
    return jsonify(data)

@app.route('/api/ai-predictions')
def api_ai_predictions():
    global ai_cache
    current_time = time.time()
    
    # Only update AI predictions every 5 minutes (300 seconds)
    if current_time - ai_cache["timestamp"] > 300 or ai_cache["data"] is None:
        print("Generating new AI predictions...")
        match_data = get_live_match_data()
        predictions = generate_ai_predictions(match_data)
        ai_cache["timestamp"] = current_time
        ai_cache["data"] = predictions
        
    return jsonify({
        "predictions": ai_cache["data"], 
        "next_update_in_seconds": int(300 - (current_time - ai_cache["timestamp"]))
    })

@app.route('/api/predictions', methods=['GET', 'POST'])
def handle_predictions():
    if request.method == 'POST':
        data = request.json
        user_predictions.append({
            "name": data.get("name", "Unknown"),
            "predicted_winner": data.get("predicted_winner"),
            "predicted_ind_score": data.get("predicted_ind_score"),
            "predicted_eng_score": data.get("predicted_eng_score")
        })
        return jsonify({"status": "success", "message": "Prediction saved!"})
    
    # GET request returns all friends' predictions
    return jsonify(user_predictions)

if __name__ == '__main__':
    # Make sure to run inside the folder where the "templates" directory exists.
    app.run(debug=True, port=5000)
