import os
import time
import random
import csv
import io
import math
from flask import Flask, render_template, request, jsonify, send_file
import psycopg2

app = Flask(__name__)

# Password from Render Environment Variables
TEACHER_PASSWORD = os.environ.get('TEACHER_PASSWORD', 'smartyes7')

# Concurrent Multi-Teacher Active Sessions
active_sessions = {}

# Distance Calculation (Haversine Formula) in Meters
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lon2) - float(lon1))

    a = math.sin(delta_phi / 2.0)**2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

def get_db_connection():
    database_url = os.environ.get('DATABASE_URL')
    conn = psycopg2.connect(database_url)
    return conn

def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id SERIAL PRIMARY KEY,
                roll_no TEXT,
                student_name TEXT,
                student_class TEXT,
                subject TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print("DB Init Error:", e)

@app.route('/', methods=['GET', 'POST'])
def home():
    init_db()
    records = []
    teacher_logged_in = False
    
    filter_date = request.form.get("filter_date")
    filter_class = request.form.get("filter_class")
    filter_subject = request.form.get("filter_subject")
    teacher_pass = request.form.get("view_password")

    if request.method == 'POST' and teacher_pass:
        if teacher_pass == TEACHER_PASSWORD:
            teacher_logged_in = True
            try:
                conn = get_db_connection()
                cursor = conn.cursor()

                query = "SELECT roll_no, student_name, student_class, subject, timestamp FROM attendance WHERE 1=1"
                params = []

                if filter_date:
                    query += " AND DATE(timestamp) = %s"
                    params.append(filter_date)
                if filter_class:
                    query += " AND student_class = %s"
                    params.append(filter_class)
                if filter_subject:
                    query += " AND subject ILIKE %s"
                    params.append(f"%{filter_subject}%")

                # Roll Number Wise Sorting
                query += " ORDER BY roll_no ASC"

                cursor.execute(query, tuple(params))
                records = cursor.fetchall()
                cursor.close()
                conn.close()
            except Exception as e:
                print("Error fetching records:", e)
        else:
            return render_template("index.html", error="Incorrect Password!")

    return render_template("index.html", records=records, teacher_logged_in=teacher_logged_in)

@app.route("/generate_code", methods=["POST"])
def generate_code():
    password = request.form.get("password")
    selected_class = request.form.get("selected_class")
    subject = request.form.get("subject")
    lat = request.form.get("latitude")
    lon = request.form.get("longitude")

    if password == TEACHER_PASSWORD:
        code = str(random.randint(100, 999))
        active_sessions[code] = {
            "class": selected_class,
            "subject": subject,
            "created_at": time.time(),
            "latitude": lat,
            "longitude": lon
        }
        return jsonify({"status": "success", "code": code, "class": selected_class, "subject": subject})
    else:
        return jsonify({"status": "error", "message": "Incorrect Teacher Password!"}), 401

@app.route("/mark_attendance", methods=["POST"])
def mark_attendance():
    code = request.form.get("code")
    roll_no = request.form.get("roll_no")
    student_name = request.form.get("student_name")
    student_lat = request.form.get("latitude")
    student_lon = request.form.get("longitude")

    if code not in active_sessions:
        return jsonify({"status": "error", "message": "Invalid or Expired Code!"}), 400

    session_info = active_sessions[code]

    # Time Expiry Check (3 Minutes)
    if time.time() - session_info["created_at"] > 180:
        del active_sessions[code]
        return jsonify({"status": "error", "message": "Code Expired!"}), 400

    # GPS Location Verification (100m Range Limit)
    if session_info.get("latitude") and student_lat:
        distance = calculate_distance(session_info["latitude"], session_info["longitude"], student_lat, student_lon)
        if distance > 100:
            return jsonify({"status": "error", "message": f"You are outside the classroom area! ({int(distance)}m away)"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO attendance (roll_no, student_name, student_class, subject)
            VALUES (%s, %s, %s, %s)
        ''', (roll_no, student_name, session_info["class"], session_info["subject"]))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success", "message": "Attendance Marked Successfully!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/download_excel", methods=["POST"])
def download_excel():
    password = request.form.get("excel_password")
    if password != TEACHER_PASSWORD:
        return "Unauthorized Access", 401

    filter_date = request.form.get("filter_date")
    filter_class = request.form.get("filter_class")
    filter_subject = request.form.get("filter_subject")

    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT roll_no, student_name, student_class, subject, timestamp FROM attendance WHERE 1=1"
    params = []

    if filter_date:
        query += " AND DATE(timestamp) = %s"
        params.append(filter_date)
    if filter_class:
        query += " AND student_class = %s"
        params.append(filter_class)
    if filter_subject:
        query += " AND subject ILIKE %s"
        params.append(f"%{filter_subject}%")

    query += " ORDER BY roll_no ASC"

    cursor.execute(query, tuple(params))
    records = cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Roll No', 'Student Name', 'Class', 'Subject', 'Date & Time'])

    for row in records:
        writer.writerow(row)

    output.seek(0)
    cursor.close()
    conn.close()

    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype="text/csv",
        as_attachment=True,
        download_name="SmartYes_Attendance_Report.csv"
    )

if __name__ == '__main__':
    app.run(debug=True)
