"""
TRIP.AI - STRICT LIVE DATA EDITION (V6.1)
Architecture: Flask + Groq Llama 3.1 + TiDB Cloud (MySQL)
Features: NO FAKE DATA. ONLY LIVE MARKET PRICES.
"""

import os
import json
import logging
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

# Load Environment Variables from .env file
load_dotenv()

# --- 1. SYSTEM LOGGING & CONFIG ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LIVE_ENGINE")

app = Flask(__name__)
# Enable CORS for live deployment
CORS(app)

# --- 2. CLOUD ENVIRONMENT VARIABLES ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_NAME = os.getenv("DB_NAME", "test")
DB_PORT = os.getenv("DB_PORT", "4000")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

# Initialize AI Client
client = Groq(api_key=GROQ_API_KEY)

# --- 3. SECURE DATABASE CONNECTOR ---
def get_db_connection():
    """Connects to TiDB Cloud using a secure TLS connection."""
    try:
        connection = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            port=DB_PORT,
            ssl_verify_cert=True,
            ssl_ca='/etc/ssl/certs/ca-certificates.crt'
        )
        return connection
    except Error as e:
        logger.error(f"DATABASE CONNECTION FAILED: {e}")
        return None

# --- 4. STRICT LIVE DATA ENGINES (NO FAKES ALLOWED) ---
def get_live_flight_price(origin, destination, date):
    if not SERPAPI_KEY:
        return "Live Price Unavailable", "#"
        
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_flights",
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": date,
        "currency": "INR",
        "hl": "en",
        "api_key": SERPAPI_KEY
    }

    try:
        response = requests.get(url, params=params).json()
        best_flight = response.get('best_flights', [{}])[0]
        price = best_flight.get('price')
        
        if not price:
            return "Live Price Unavailable", "#"
            
        booking_url = f"https://www.google.com/travel/flights?q=Flights%20to%20{destination}%20from%20{origin}%20on%20{date}"
        return f"₹{price}", booking_url
    except Exception as e:
        logger.error(f"Flight API Error: {e}")
        return "Live Price Unavailable", "#"

def get_live_hotel_price(destination, check_in_date):
    if not SERPAPI_KEY:
        return "Live Price Unavailable"
        
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_hotels",
        "q": f"Hotels in {destination}",
        "check_in_date": check_in_date,
        "check_out_date": check_in_date,
        "currency": "INR",
        "api_key": SERPAPI_KEY
    }
    
    try:
        response = requests.get(url, params=params).json()
        # Grab the price of the first recommended property
        price = response.get('properties', [{}])[0].get('total_rate')
        
        if not price:
            return "Live Price Unavailable"
        return f"₹{price}"
    except Exception as e:
        logger.error(f"Hotel API Error: {e}")
        return "Live Price Unavailable"

def get_weather_and_coords(city_name):
    """Fetches weather and coordinates (Lat/Lon) for map animations."""
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&language=en&format=json"
        geo_res = requests.get(geo_url).json()
        
        if not geo_res.get('results'):
            return "Weather unavailable", 0, 0
            
        lat = geo_res['results'][0]['latitude']
        lon = geo_res['results'][0]['longitude']

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        w_res = requests.get(weather_url).json()
        
        temp = w_res['current_weather']['temperature']
        return f"{temp}°C", lat, lon
    except Exception as e:
        logger.error(f"Weather/Geo Error: {e}")
        return "Standard conditions", 0, 0

# --- 5. PRIMARY API ROUTES ---

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "active", "engine": "Llama 3.1 8B Strict Live"}), 200

@app.route('/api/generate_trip', methods=['POST'])
def generate_trip():
    data = request.json
    origin = data.get('origin', 'BOM')
    dest = data.get('destination', 'DXB')
    dur = int(data.get('duration', 3))
    pax = int(data.get('passengers', 1))
    style = data.get('budgetType', 'Moderate')
    travel_date = data.get('departureDate')

    logger.info(f"STARTING STRICT LIVE MANIFEST: {origin} -> {dest} for {pax} pax")

    # STRICT STEP A: REAL-TIME MARKET DISCOVERY
    real_flight_price, booking_link = get_live_flight_price(origin, dest, travel_date)
    real_hotel_price = get_live_hotel_price(dest, travel_date)
    
    dest_weather, dest_lat, dest_lon = get_weather_and_coords(dest)
    _, orig_lat, orig_lon = get_weather_and_coords(origin)

    # STRICT STEP B: AI PROMPT (FORCED TO USE REAL NUMBERS)
    prompt = f"""
    You are an enterprise travel agent. Design a bespoke {dur}-day itinerary for {dest} starting from {origin} for {pax} travelers.
    Travel Style: {style}. Local Weather: {dest_weather}.
    
    CRITICAL LIVE MARKET DATA:
    - Live Flight Price: {real_flight_price}
    - Live Hotel Price (per night): {real_hotel_price}
    
    INSTRUCTIONS:
    1. Do NOT invent fake prices. If the data says "Live Price Unavailable", output exactly "Live Price Unavailable".
    2. If a real Hotel Price is provided, multiply it by {dur} days for the total hotel budget.
    3. Estimate a realistic "Daily Activities" budget based on the '{style}' travel style.
    4. Calculate the Final Total mathematically based ONLY on the live prices provided + your estimated activities budget.
    
    Return ONLY a JSON object with this exact structure:
    {{
      "coordinates": {{"origin": [{orig_lat}, {orig_lon}], "dest": [{dest_lat}, {dest_lon}]}},
      "booking_url": "{booking_link}",
      "weather_advice": "Specific clothing advice based on {dest_weather}",
      "financials": {{
        "flights": "{real_flight_price}",
        "hotels": "Calculated total hotel price OR 'Live Price Unavailable'",
        "activities": "Estimated activities budget",
        "total": "Calculated Total Budget"
      }},
      "itinerary": [
        {{
          "day": 1,
          "theme": "A creative title",
          "morning": "Activity description",
          "afternoon": "Activity description",
          "evening": "Activity description"
        }}
      ]
    }}
    """

    try:
        # Step D: AI Inference
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a professional travel API. Only return valid JSON. Never invent fake flight/hotel data."},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.1-8b-instant",
            response_format={"type": "json_object"}
        )
        
        itinerary_json = response.choices[0].message.content
        
        # Step E: Save to TiDB Cloud Database
        db = get_db_connection()
        if db:
            cursor = db.cursor()
            query = "INSERT INTO trips (destination, duration, budget_type, itinerary) VALUES (%s, %s, %s, %s)"
            cursor.execute(query, (dest, dur, style, itinerary_json))
            db.commit()
            cursor.close()
            db.close()
            logger.info("Trip successfully archived to TiDB Cloud.")

        return jsonify({
            "status": "success", 
            "itinerary": itinerary_json, 
            "raw_weather": dest_weather 
        })
    except Exception as e:
        logger.error(f"ENGINE ERROR: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/past_trips', methods=['GET'])
def get_past_trips():
    """Fetches the latest itineraries from the database for the Dashboard."""
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
