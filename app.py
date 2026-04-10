"""
TRIP.AI - ENTERPRISE CLOUD EDITION (V6.0)
Architecture: Flask + Groq Llama 3.1 + TiDB Cloud (MySQL)
Features: Live Flights, Live Hotels, Weather, Route Coordinates, Vault Persistence
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

# --- 1. SYSTEM LOGGING & CONFIG ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CLOUD_ENGINE")

app = Flask(__name__)
# Enable CORS for live deployment
CORS(app)

# --- 2. CLOUD ENVIRONMENT VARIABLES ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")
DB_HOST = os.getenv("DB_HOST", "gateway01.ap-southeast-1.prod.aws.tidbcloud.com")
DB_USER = os.getenv("DB_USER", "3ckvtyMQiMcjj6o.root")
DB_PASS = os.getenv("DB_PASS", "W1F1QQ3NPZW4KWKR")
DB_NAME = os.getenv("DB_NAME", "test")
DB_PORT = os.getenv("DB_PORT", "4000")
SERPAPI_KEY = os.getenv("SERPAPI_KEY") # Add this to Render!

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

# --- 4. LIVE DATA ENGINES ---
def get_live_flight_price(origin, destination, date):
    if not SERPAPI_KEY:
        return "N/A", "#"
        
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
        price = best_flight.get('price', 'N/A')
        booking_url = f"https://www.google.com/travel/flights?q=Flights%20to%20{destination}%20from%20{origin}%20on%20{date}"
        return price, booking_url
    except Exception as e:
        logger.error(f"Flight API Error: {e}")
        return "N/A", "#"

def get_live_hotel_price(destination, check_in_date):
    if not SERPAPI_KEY:
        return "N/A"
        
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_hotels",
        "q": f"Hotels in {destination}",
        "check_in_date": check_in_date,
        "check_out_date": check_in_date, # Simplified for MVP single night metric
        "currency": "INR",
        "api_key": SERPAPI_KEY
    }
    
    try:
        response = requests.get(url, params=params).json()
        # Grab the price of the first recommended property
        price = response.get('properties', [{}])[0].get('total_rate', 'N/A')
        return price
    except Exception as e:
        logger.error(f"Hotel API Error: {e}")
        return "N/A"

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

def calculate_trip_economics(style, duration, passengers):
    """Fallback simulated market prices."""
    tiers = {
        "Budget": {"air": 35000, "hotel": 1500, "daily": 2000},
        "Moderate": {"air": 75000, "hotel": 7500, "daily": 6000},
        "Luxury": {"air": 220000, "hotel": 35000, "daily": 25000}
    }
    config = tiers.get(style, tiers["Moderate"])
    
    air_total = config["air"] * passengers
    hotel_total = config["hotel"] * duration
    spend_total = config["daily"] * duration
    
    return {
        "airfare": f"{air_total:,}",
        "lodging": f"{hotel_total:,}",
        "spending": f"{spend_total:,}",
        "total": f"{air_total + hotel_total + spend_total:,}"
    }

# --- 5. PRIMARY API ROUTES ---

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({"status": "active", "engine": "Llama 3.1 8B"}), 200

@app.route('/api/generate_trip', methods=['POST'])
def generate_trip():
    data = request.json
    origin = data.get('origin', 'BOM')
    dest = data.get('destination', 'DXB')
    dur = int(data.get('duration', 3))
    pax = int(data.get('passengers', 1))
    style = data.get('budgetType', 'Moderate')
    travel_date = data.get('departureDate')

    logger.info(f"STARTING LIVE MANIFEST: {origin} -> {dest} for {pax} pax")

    # STEP A: REAL-TIME MARKET DISCOVERY (Flights, Hotels, Weather, Coords)
    real_flight_price, booking_link = get_live_flight_price(origin, dest, travel_date)
    real_hotel_price = get_live_hotel_price(dest, travel_date)
    
    dest_weather, dest_lat, dest_lon = get_weather_and_coords(dest)
    _, orig_lat, orig_lon = get_weather_and_coords(origin)

    # STEP B: SECONDARY ECONOMICS
    finances = calculate_trip_economics(style, dur, pax)
    if real_flight_price != "N/A":
        finances['airfare'] = real_flight_price
    if real_hotel_price != "N/A":
        # Multiply daily hotel rate by duration
        try:
            clean_price = int(str(real_hotel_price).replace(',', '').replace('₹', '').strip())
            finances['lodging'] = f"{clean_price * dur:,}"
        except:
            finances['lodging'] = real_hotel_price

    # STEP C: AI PROMPT ENGINEERING
    prompt = f"""
    You are a luxury travel agent. Design a bespoke {dur}-day itinerary for {dest} starting from {origin}.
    Travel Style: {style}. Local Weather: {dest_weather}.
    
    Return ONLY a JSON object with this exact structure:
    {{
      "coordinates": {{"origin": [{orig_lat}, {orig_lon}], "dest": [{dest_lat}, {dest_lon}]}},
      "booking_url": "{booking_link}",
      "weather_advice": "Specific clothing advice based on {dest_weather}",
      "financials": {{
        "flights": "{finances['airfare']}",
        "hotels": "{finances['lodging']}",
        "activities": "{finances['spending']}",
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
                {"role": "system", "content": "You are a professional travel API. Only return valid JSON."},
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

        return jsonify({"status": "success", "itinerary": itinerary_json})

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