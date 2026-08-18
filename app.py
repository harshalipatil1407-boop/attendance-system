import os
import random
import sqlite3
from datetime import datetime
from flask import Flask, jsonify, render_template, request

# Try importing PostgreSQL adapter if available
try:
    import psycopg2
except ImportError:
    psycopg2 = None

app = Flask(__name__)

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    # Agar Render par DATABASE_URL set hai toh PostgreSQL use karo
    if DATABASE_URL:
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(url)
    else:
        # Local system ke liye SQLite fallback
        return sqlite3.connect("attendance.db")

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # PostgreSQL / SQLite dono ke liye standard query
    if DATABASE_URL:
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
    class_name = request.form.get("class_name")
    division = request.form.get("division")
    subject = request.form.get("subject")
    period = request.form.get("period")
    teacher_lat = float(request.form.get("latitude", 0))
    teacher_lon = float(request.form.get("longitude", 0))

    session_key = f"{class_name}_{division}"
    code = str(random.randint(100, 999))

    active_sessions[session_key] = {
        "code": code,
        "subject": subject,
        "period": period,
        "teacher_lat": teacher_lat,
        "teacher_lon": teacher_lon,
        "generated_at": datetime.now(),
    }

    return jsonify({
        "status": "Success",
        "code": code,
        "message": (
            f"Code generated for {class_name} Div {division} - {subject}"
            f" ({period})"
        ),
    })

@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():
    class_name = request.form.get("class_name")
    division = request.form.get("division")
    roll_no = request.form.get("roll_no")
    entered_code = request.form.get("code")
    user_lat = float(request.form.get("latitude", 0))
    user_lon = float(request.form.get("longitude", 0))

    session_key = f"{class_name}_{division}"

    if session_key not in active_sessions:
        return jsonify({
            "status": "Failed",
            "reason": "No active class session found for your Class/Division!",
        })

    session_data = active_sessions[session_key]

    if entered_code != session_data["code"]:
        return jsonify(
            {"status": "Failed", "reason": "Invalid or Expired Class Code!"}
        )
