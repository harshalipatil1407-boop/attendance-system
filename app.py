import os
import re
import random
import sqlite3
from math import radians, cos, sin, asin, sqrt
from datetime import datetime
from flask import Flask, jsonify, render_template, request

try:
    import psycopg2
except ImportError:
    psycopg2 = None

app = Flask(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL')

def clean_input(text):
    if not text:
        return ""
    cleaned = re.sub(r'(?i)class|division', '', str(text)).strip().upper()
    return cleaned if cleaned else str(text).strip().upper()

# Distance calculation (Haversine Formula) in meters
def calculate_distance(lat1, lon1, lat2, lon2):
    try:
        r = 6371000  # Radius of Earth in meters
        lat1, lon1, lat2, lon2 = map(radians, [float(lat1), float(lon1), float(float(lat2)), float(lon2)])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
        return r * 2 * asin(sqrt(a))
    except Exception:
        return 0

def get_db_connection():
    if DATABASE_URL and psycopg2:
        try:
            url = DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            return psycopg2.connect(url), "postgres"
        except Exception:
            return sqlite3.connect("attendance.db"), "sqlite"
    else:
        return sqlite3.connect("attendance.db"), "sqlite"

def init_db():
    conn, db_type = get_db_connection()
    cursor = conn.cursor()
    if db_type == "postgres":
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id SERIAL PRIMARY KEY,
                date TEXT,
                time TEXT,
                class_name TEXT,
                division TEXT,
                subject TEXT,
                period TEXT,
                roll_no TEXT,
                status TEXT
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT,
                time TEXT,
                class_name TEXT,
                division TEXT,
                subject TEXT,
                period TEXT,
                roll_no TEXT,
                status TEXT
            )
        """)
    conn.commit()
    conn.close()

init_db()

active_sessions = {}

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/generate_code", methods=["POST"])
def generate_code():
    try:
        raw_class = request.form.get("class_name", "")
        raw_div = request.form.get("division", "")
        
        class_name = clean_input(raw_class)
        division = clean_input(raw_div)
        subject = str(request.form.get("subject", "")).strip()
        period = str(request.form.get("period", "")).strip()
        lat = request.form.get("latitude", 0)
        lon = request.form.get("longitude", 0)

        session_key = f"{class_name}_{division}"
        code = str(random.randint(100, 999))

        active_sessions[session_key] = {
            "code": code,
            "subject": subject,
            "period": period,
            "lat": lat,
            "lon": lon,
            "generated_at": datetime.now(),
        }

        return jsonify({
            "status": "Success",
            "code": code,
            "message": f"Code generated for {raw_class} {raw_div}"
        })
    except Exception as e:
        return jsonify({"status": "Failed", "reason": f"Teacher Error: {str(e)}"})

@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():
    try:
        raw_class = request.form.get("class_name", "")
        raw_div = request.form.get("division", "")
        
        class_name = clean_input(raw_class)
        division = clean_input(raw_div)
        roll_no = str(request.form.get("roll_no", "")).strip()
        entered_code = str(request.form.get("code", "")).strip()
        user_lat = request.form.get("latitude", 0)
        user_lon = request.form.get("longitude", 0)

        session_key = f"{class_name}_{division}"

        # 1. Active Session Check
        if session_key not in active_sessions:
            return jsonify({
                "status": "Failed",
                "reason": f"No active session found for '{raw_class}' '{raw_div}'! Code generate karne ke baad hi attendance mark karein."
            })

        session_data = active_sessions[session_key]

        # 2. Code Verification Check
        if entered_code != session_data["code"]:
            return jsonify({
                "status": "Failed",
                "reason": f"Invalid Code! Correct code is: {session_data['code']}"
            })

        # 3. Location / Distance Verification Check (50 Meters Radius)
        if session_data["lat"] != 0 and user_lat != 0:
            dist = calculate_distance(session_data["lat"], session_data["lon"], user_lat, user_lon)
            if dist > 50:  # Allow max 50 meters distance
                return jsonify({
                    "status": "Failed",
                    "reason": f"You are out of classroom range! (Distance: {int(dist)}m)"
                })

        # 4. Save to Database
        now = datetime.now()
        current_date = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M:%S")

        conn, db_type = get_db_connection()
        cursor = conn.cursor()

        if db_type == "postgres":
            cursor.execute("""
                INSERT INTO attendance_logs (date, time, class_name, division, subject, period, roll_no, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                current_date, current_time, class_name, division,
                session_data["subject"], session_data["period"], roll_no, "Present"
            ))
        else:
            cursor.execute("""
                INSERT INTO attendance_logs (date, time, class_name, division, subject, period, roll_no, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                current_date, current_time, class_name, division,
                session_data["subject"], session_data["period"], roll_no, "Present"
            ))

        conn.commit()
        conn.close()

        return jsonify({
            "status": "Success",
            "message": f"Attendance Marked Successfully for Roll No {roll_no}!"
        })

    except Exception as e:
        return jsonify({
            "status": "Failed",
            "reason": f"Server Error: {str(e)}"
        })
