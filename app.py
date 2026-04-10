"""
TRIP.AI - THE ABSOLUTE CLOUD EDITION (V5.0)
Architecture: Flask + Groq Llama 3.1 + TiDB Cloud (MySQL)
Features: Financial Forecasting, Itinerary Generation, Cloud Persistence
"""

import os
import json
import random
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
import mysql.connector
from mysql.connector import Error

# --- 1. SYSTEM LOGGING & CONFIG ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CLOUD_ENGINE")

app = Flask(__name__)
# Enable CORS for live deployment
CORS(app)

# --- 2. CLOUD ENVIRONMENT VARIABLES ---
# These will be set in the Render.com dashboard under 'Environment'
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")
DB_HOST = os.getenv("DB_HOST", "gateway01.ap-southeast-1.prod.aws.tidbcloud.com")
DB_USER = os.getenv("DB_USER", "3ckvtyMQiMcjj6o.root")
DB_PASS = os.getenv("DB_PASS", "W1F1QQ3NPZW4KWKR")
DB_NAME = os.getenv("DB_NAME", "test")
DB_PORT = os.getenv("DB_PORT", "4000")

# Initialize AI Client
client = Groq(api_key=GROQ_API_KEY)

# --- 3. SECURE DATABASE CONNECTOR ---
def get_db_connection():
    """
    Connects to TiDB Cloud using a secure TLS connection.
    On Render (Linux), the CA bundle is at /etc/ssl/certs/ca-certificates.crt
    """
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            port=DB_PORT,
            ssl_verify_cert=True,
            ssl_ca='/etc/ssl/certs/ca-certificates.crt' # Required for Cloud Security
        )
        return connection
    except Error as e:
        logger.error(f"DATABASE CONNECTION FAILED: {e}")
        return None

# --- 4. FINANCIAL INTELLIGENCE UNIT ---
def calculate_trip_economics(style, duration, passengers):
    """
    Generates a simulated market price for Flights and Hotels based on the tier.
    Prices are calculated in Indian Rupees (INR) for local relevance.
    """
    tiers = {
        "Backpacker": {"air": 35000, "hotel": 1500, "daily": 2000},
        "Moderate": {"air": 75000, "hotel": 7500, "daily": 6000},
        "Luxury": {"air": 220000, "hotel": 35000, "daily": 25000}
    }
    
    config = tiers.get(style, tiers["Moderate"])
    
    # Calculate totals
    air_total = config["air"] * passengers
    hotel_total = config["hotel"] * duration
    spend_total = config["daily"] * duration
    
    return {
        "airfare": f"₹{air_total:,}",
        "lodging": f"₹{hotel_total:,}",
        "spending": f"₹{spend_total:,}",
        "total": f"₹{air_total + hotel_total + spend_total:,}"
    }

# --- 5. PRIMARY API ROUTES ---

@app.route('/api/health', methods=['GET'])
def health():
    """Service health check for Render monitoring."""
    return jsonify({"status": "active", "engine": "Llama 3.1 8B"}), 200

@app.route('/api/generate_trip', methods=['POST'])
def generate_trip():
    """
    The main engine: 
    1. Performs cost estimation
    2. Generates AI Itinerary 
    3. Saves to Cloud Database
    """
    data = request.json
    origin = data.get('origin', 'Mumbai')
    dest = data.get('destination', 'Paris')
    dur = int(data.get('duration', 3))
    pax = int(data.get('passengers', 1))
    style = data.get('budgetType', 'Moderate')
    
    logger.info(f"STARTING MANIFEST: {dest} for {pax} people")

    # Step A: Financial Analysis
    finances = calculate_trip_economics(style, dur, pax)

    # Step B: AI Prompt Engineering
    prompt = f"""
    You are a luxury travel agent. Design a bespoke {dur}-day itinerary for {dest} starting from {origin}.
    Travel Style: {style}. Total Estimated Budget: {finances['total']}.
    
    Return ONLY a JSON object with this exact structure:
    {{
      "financials": {{
        "flights": "{finances['airfare']}",
        "hotels": "{finances['lodging']}",
        "activities": "{finances['spending']}",
        "total": "{finances['total']}"
      }},
      "itinerary": [
        {{
          "day": 1,
          "theme": "A creative title for the day",
          "morning": "Detailed luxury morning activity string",
          "afternoon": "Sophisticated afternoon activity string",
          "evening": "Premium night activity string"
        }}
      ]
    }}
    """

    try:
        # Step C: AI Inference
        response = client.chat.completions.create(
            messages=[{"role": "system", "content": "You are a professional travel API."},
                      {"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            response_format={"type": "json_object"}
        )
        
        itinerary_json = response.choices[0].message.content
        
        # Step D: Save to Cloud Database
        db = get_db_connection()
        if db:
            cursor = db.cursor()
            query = "INSERT INTO trips (destination, duration, budget_type, itinerary) VALUES (%s, %s, %s, %s)"
            cursor.execute(query, (dest, dur, style, itinerary_json))
            db.commit()
            cursor.close()
            db.close()
            logger.info("Trip successfully archived to TiDB Cloud.")

        return jsonify({"status": "success", "itinerary": itinerary_json})

    except Exception as e:
        logger.error(f"ENGINE ERROR: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/past_trips', methods=['GET'])
def get_past_trips():
    """Fetches the latest itineraries from the database."""
    db = get_db_connection()
    if not db: return jsonify([])
    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id, destination, duration, created_at FROM trips ORDER BY created_at DESC LIMIT 6")
        rows = cursor.fetchall()
        cursor.close()
        db.close()
        return jsonify(rows)
    except Exception as e:
        logger.error(f"DB FETCH ERROR: {e}")
        return jsonify([])

@app.route('/api/delete_trip/<int:trip_id>', methods=['DELETE'])
def delete_trip(trip_id):
    """Removes a specific manifest from the database."""
    db = get_db_connection()
    if not db: return jsonify({"status": "error"})
    try:
        cursor = db.cursor()
        cursor.execute("DELETE FROM trips WHERE id = %s", (trip_id,))
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Live environments provide the PORT automatically
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
    DATABASE_URL = "mysql+pymysql://3ckvtYmQiMcjj6o.root:W1F1QQ3NPZw4KWKR@gateway01.ap-southeast-1.prod.aws.tidbcloud.com:4000/test?ssl_ca=ca.pem"
