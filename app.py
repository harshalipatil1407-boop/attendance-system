import os
import random
import sqlite3
from datetime import datetime
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
DB_FILE = "attendance.db"


def init_db():
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
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

  # Dynamic GPS Check: Student vs Teacher Location (Max ~50 Meters)
  lat_diff = abs(user_lat - session_data["teacher_lat"])
  lon_diff = abs(user_lon - session_data["teacher_lon"])

  if lat_diff > 0.05 or lon_diff > 0.05:
    return jsonify({
        "status": "Failed",
        "reason": (
            "Location Verification Failed! You are too far from the teacher."
        ),
    })

  curr_date = datetime.now().strftime("%Y-%m-%d")
  curr_time = datetime.now().strftime("%I:%M:%S %p")

  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()

  cursor.execute(
      """
        SELECT id FROM attendance_logs 
        WHERE date=? AND class_name=? AND division=? AND period=? AND roll_no=?
    """,
      (curr_date, class_name, division, session_data["period"], roll_no),
  )

  if cursor.fetchone():
    conn.close()
    return jsonify(
        {"status": "Failed", "reason": "Attendance already marked for today!"}
    )

  cursor.execute(
      """
        INSERT INTO attendance_logs (date, time, class_name, division, subject, period, roll_no, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
      (
          curr_date,
          curr_time,
          class_name,
          division,
          session_data["subject"],
          session_data["period"],
          roll_no,
          "Present",
      ),
  )

  conn.commit()
  conn.close()

  return jsonify({
      "status": "Success",
      "message": (
          f"Attendance Marked Successfully! [Roll No: {roll_no} |"
          f" {session_data['subject']}]"
      ),
  })


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000, debug=True)