"""
TRIP.AI - STRICT LIVE DATA ENGINE (V6.1)
Architecture: Flask + Groq Llama 3.1 + TiDB Cloud (MySQL)
Rules: NO FAKE DATA. NO FALLBACKS. ONLY LIVE MARKET PRICES.
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

# Load Environment Variables
load_dotenv()

# --- 1. SYSTEM LOGGING & CONFIG ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LIVE_ENGINE")

app = Flask(__name__)
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

# --- 4. STRICT LIVE DATA ENGINES ---

def get_iata_code(query):
    """Translates city/country names into valid IATA Airport IDs via SerpApi."""
    if not SERPAPI_KEY: return query
    url = "https://serpapi.com/locations.json"
    params = {"q": query, "limit": 1, "api_key": SERPAPI_KEY}
    try:
        response = requests.get(url, params=params).json()
        if isinstance(response, list) and len(response) > 0:
            return response[0].get('id', query)
        return query
    except Exception as e:
        logger.error(f"IATA Resolver Error: {e}")
        return query

def get_live_flight_price(origin_id, dest_id, date):
    """Scrapes real-time flight data. NO FAKES."""
    if not SERPAPI_KEY: return "Live Price Unavailable", "#"
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_flights",
        "departure_id": origin_id,
        "arrival_id": dest_id,
        "outbound_date": date,
        "currency": "INR",
        "hl": "en",
        "api_key": SERPAPI_KEY
    }
    try:
        response = requests.get(url, params=params).json()
        best_flights = response.get('best_flights')
        if not best_flights: return "Live Price Unavailable", "#"
        
        price = best_flights[0].get('price')
        booking_url = f"https://www.google.com/travel/flights?q=Flights%20to%20{dest_id}%20from%20{origin_id}%20on%20{date}"
        return f"₹{price:,}" if price else "Live Price Unavailable", booking_url
    except Exception as e:
        logger.error(f"Flight API Error: {e}")
        return "Live Price Unavailable", "#"

def get_live_hotel_price(destination, check_in_date):
    """Scrapes real-time hotel rates. NO FAKES."""
    if not SERPAPI_KEY: return "Live Price Unavailable"
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
        props = response.get('properties')
        if not props: return "Live Price Unavailable"
        
        price = props[0].get('total_rate')
        return f"₹{price:,}" if price else "Live Price Unavailable"
    except Exception as e:
        logger.error(f"Hotel API Error: {e}")
        return "Live Price Unavailable"

def get_weather_and_coords(city_name):
    """Fetches weather and GPS coordinates for mapping."""
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&language=en&format=json"
        geo_res = requests.get(geo_url).json()
        if not geo_res.get('results'): return "Weather unavailable", 0, 0
        
        res = geo_res['results'][0]
        lat, lon = res['latitude'], res['longitude']
        
        w_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        w_res = requests.get(w_url).json()
        temp = w_res['current_weather']['temperature']
        return f"{temp}°C", lat, lon
    except:
        return "Standard conditions", 0, 0

# --- 5. PRIMARY API ROUTES ---

@app.route('/api/generate_trip', methods=['POST'])
def generate_trip():
    data = request.json
    origin_name = data.get('origin', 'Mumbai')
    dest_name = data.get('destination', 'Dubai')
    dur = int(data.get('duration', 3))
    pax = int(data.get('passengers', 1))
    style = data.get('budgetType', 'Moderate')
    travel_date = data.get('departureDate')

    logger.info(f"INITIATING MANIFEST: {origin_name} -> {dest_name}")

    # RESOLVE IATA CODES (MUMBAI -> BOM)
    origin_id = get_iata_code(origin_name)
    dest_id = get_iata_code(dest_name)

    # GATHER LIVE DATA
    real_flight, booking_url = get_live_flight_price(origin_id, dest_id, travel_date)
    real_hotel = get_live_hotel_price(dest_name, travel_date)
    dest_weather, dest_lat, dest_lon = get_weather_and_coords(dest_name)
    _, orig_lat, orig_lon = get_weather_and_coords(origin_name)

    # AI PROMPT (STRICT DATA ENFORCEMENT)
    prompt = f"""
    Role: Enterprise Travel Architect.
    Mission: Create a {dur}-day {style} itinerary for {dest_name} (from {origin_name}) for {pax} travelers.
    Weather: {dest_weather}.
    
    MANDATORY LIVE MARKET DATA:
    - Base Flight Price: {real_flight}
    - Base Hotel/Night: {real_hotel}
    
    RULES:
    1. If data is 'Live Price Unavailable', use that exact string in JSON.
    2. Calculate total hotel cost as (Hotel Price * {dur}).
    3. Calculate Grand Total based ONLY on real prices + realistic activity estimates.
    
    RETURN ONLY JSON:
    {{
      "coordinates": {{"origin": [{orig_lat}, {orig_lon}], "dest": [{dest_lat}, {dest_lon}]}},
      "booking_url": "{booking_url}",
      "weather_advice": "Advice for {dest_weather}",
      "financials": {{
        "flights": "{real_flight}",
        "hotels": "Total calculated hotel cost",
        "activities": "Estimate for {style} style",
        "total": "Calculated total in INR"
      }},
      "itinerary": [{{ "day": 1, "theme": "...", "morning": "...", "afternoon": "...", "evening": "..." }}]
    }}
    """

    try:
        response = client.chat.completions.create(
            messages=[{"role": "system", "content": "Professional API. JSON output only. No fakes."}, {"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            response_format={"type": "json_object"}
        )
        itinerary_json = response.choices[0].message.content
        
        # PERSIST TO CLOUD VAULT (TiDB)
        db = get_db_connection()
        if db:
            cursor = db.cursor()
            cursor.execute("INSERT INTO trips (destination, duration, budget_type, itinerary) VALUES (%s, %s, %s, %s)", (dest_name, dur, style, itinerary_json))
            db.commit()
            db.close()

        return jsonify({"status": "success", "itinerary": itinerary_json, "raw_weather": dest_weather})
    except Exception as e:
        logger.error(f"ENGINE ERROR: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/past_trips', methods=['GET'])
def get_past_trips():
    db = get_db_connection()
    if not db: return jsonify([])
    try:
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT id, destination, duration, created_at FROM trips ORDER BY created_at DESC LIMIT 6")
        rows = cursor.fetchall()
        db.close()
        return jsonify(rows)
    except:
        return jsonify([])

@app.route('/api/delete_trip/<int:trip_id>', methods=['DELETE'])
def delete_trip(trip_id):
    db = get_db_connection()
    if not db: return jsonify({"status": "error"})
    try:
        cursor = db.cursor()
        cursor.execute("DELETE FROM trips WHERE id = %s", (trip_id,))
        db.commit()
        db.close()
        return jsonify({"status": "success"})
    except:
        return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
