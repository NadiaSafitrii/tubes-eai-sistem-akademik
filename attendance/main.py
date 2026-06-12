import time
import threading
import json
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime
import pika
from fastapi import FastAPI, Response, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
from typing import Union

# Database configuration
DB_FILE = "attendance.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Only drop the legacy attendance_logs table
    cursor.execute("DROP TABLE IF EXISTS attendance_logs")
    
    # Create students table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name TEXT,
            is_active INTEGER DEFAULT 0,
            updated_at TEXT
        )
    """)
    # Create classes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            class_id TEXT PRIMARY KEY,
            name TEXT
        )
    """)
    # Create enrollments table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            class_id TEXT,
            UNIQUE(student_id, class_id),
            FOREIGN KEY(student_id) REFERENCES students(student_id),
            FOREIGN KEY(class_id) REFERENCES classes(class_id)
        )
    """)
    # Create attendance_sessions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            class_id TEXT,
            meeting_number INTEGER,
            attendance_date TEXT,
            created_at TEXT,
            FOREIGN KEY(class_id) REFERENCES classes(class_id)
        )
    """)
    # Create attendance_details table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            student_id TEXT,
            status TEXT,
            created_at TEXT,
            UNIQUE(session_id, student_id),
            FOREIGN KEY(session_id) REFERENCES attendance_sessions(id),
            FOREIGN KEY(student_id) REFERENCES students(student_id)
        )
    """)
    
    # Seed default classes
    default_classes = [
        ("EAI-A", "Enterprise Application Integration"),
        ("BPM-A", "Business Process Management"),
        ("IF-44-01", "Informatika 44-01")
    ]
    for class_id, name in default_classes:
        cursor.execute("""
            INSERT INTO classes (class_id, name)
            VALUES (?, ?)
            ON CONFLICT(class_id) DO UPDATE SET name=excluded.name
        """, (class_id, name))
        
    conn.commit()
    
    # Active Student Sync from SIAKAD
    retries = 5
    for attempt in range(retries):
        try:
            import urllib.request
            import json
            import time
            siakad_url = "http://siakad:8001/students"
            req = urllib.request.Request(siakad_url)
            with urllib.request.urlopen(req, timeout=5) as response:
                students_list = json.loads(response.read().decode())
                print(f"[Attendance Sync] Syncing {len(students_list)} students from SIAKAD...")
                for s in students_list:
                    student_id = s.get("student_id")
                    name = s.get("name")
                    status = s.get("status")
                    classes = s.get("classes", [])
                    
                    # Sync all active students
                    if status == "active":
                        cursor.execute("""
                            INSERT INTO students (student_id, name, is_active, updated_at)
                            VALUES (?, ?, 1, ?)
                            ON CONFLICT(student_id) DO UPDATE SET name=excluded.name, is_active=1
                        """, (student_id, name, datetime.utcnow().isoformat() + "Z"))
                        
                        for cls in classes:
                            class_id = cls.get("id")
                            class_name = cls.get("name")
                            if class_id:
                                cursor.execute("""
                                    INSERT INTO classes (class_id, name)
                                    VALUES (?, ?)
                                    ON CONFLICT(class_id) DO UPDATE SET name=excluded.name
                                """, (class_id, class_name or class_id))
                                
                                cursor.execute("""
                                    INSERT INTO enrollments (student_id, class_id)
                                    VALUES (?, ?)
                                    ON CONFLICT(student_id, class_id) DO NOTHING
                                """, (student_id, class_id))
                conn.commit()
                print("[Attendance Sync] Successfully synced active students and enrollments from SIAKAD.")
                break
        except Exception as e:
            print(f"[Attendance Sync Warning] Attempt {attempt+1}/{retries} failed to sync active students on startup: {e}")
            if attempt < retries - 1:
                time.sleep(2)
        
    conn.close()
    print("SQLite Database initialized and default classes seeded successfully in Attendance service.")


# RabbitMQ configuration
RABBITMQ_HOST = "rabbitmq"
RABBITMQ_PORT = 5672

def connect_rabbitmq():
    retries = 12
    connection = None
    while retries > 0:
        try:
            print("Connecting to RabbitMQ...")
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT)
            )
            print("Successfully connected to RabbitMQ.")
            return connection
        except pika.exceptions.AMQPConnectionError:
            print("RabbitMQ not ready. Retrying in 5 seconds...")
            time.sleep(5)
            retries -= 1
    raise Exception("Could not connect to RabbitMQ after multiple attempts.")

def start_rabbitmq_consumer():
    try:
        connection = connect_rabbitmq()
        channel = connection.channel()
        
        # Declare the student.active queue (must be durable)
        channel.queue_declare(queue="student.active", durable=True)
        
        def callback(ch, method, properties, body):
            try:
                print(f"[Attendance] Received raw queue body: {body.decode()}")
                data = json.loads(body.decode())
                
                student_id = data.get("student_id")
                event_type = data.get("event_type")
                
                print(f"[Attendance] Processing event '{event_type}' for student: {student_id}")
                
                if student_id:
                    payload = data.get("payload", {})
                    name = payload.get("name", "Unknown Student")
                    classes_list = payload.get("classes", [])
                    
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    
                    # 1. Update students table (idempotent upsert)
                    cursor.execute("""
                        INSERT INTO students (student_id, name, is_active, updated_at)
                        VALUES (?, ?, 1, ?)
                        ON CONFLICT(student_id) DO UPDATE SET name=excluded.name, is_active=1, updated_at=excluded.updated_at
                    """, (student_id, name, datetime.utcnow().isoformat() + "Z"))
                    
                    # 2. Update classes and enrollments
                    for cls in classes_list:
                        class_id = cls.get("id") or cls.get("class_id")
                        class_name = cls.get("name")
                        
                        if class_id:
                            # Insert/Update class
                            cursor.execute("""
                                INSERT INTO classes (class_id, name)
                                VALUES (?, ?)
                                ON CONFLICT(class_id) DO UPDATE SET name=excluded.name
                            """, (class_id, class_name or class_id))
                            
                            # Insert enrollment (idempotent due to UNIQUE constraint and DO NOTHING)
                            cursor.execute("""
                                INSERT INTO enrollments (student_id, class_id)
                                VALUES (?, ?)
                                ON CONFLICT(student_id, class_id) DO NOTHING
                            """, (student_id, class_id))
                            
                    conn.commit()
                    conn.close()
                    print(f"[Attendance] Student {student_id} ({name}) activated and classes mapped successfully.")
                
                ch.basic_ack(delivery_tag=method.delivery_tag)
                print(f"[Attendance] Acknowledged message.")
            except Exception as e:
                print(f"[Attendance] Error inside consumer callback: {e}")
                # Reject message without requeueing to avoid infinite loop
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        # Set QoS prefetch count to 1
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue="student.active", on_message_callback=callback)
        print("[Attendance] RabbitMQ consumer listening on 'student.active' queue...")
        channel.start_consuming()
    except Exception as e:
        print(f"[Attendance] RabbitMQ consumer main runner error: {e}")

# Helper function to generate XML responses
def to_xml_response(root: ET.Element, status_code: int = 200) -> Response:
    xml_bytes = ET.tostring(root, encoding="utf-8", method="xml")
    declaration = b'<?xml version="1.0" encoding="utf-8"?>\n'
    return Response(
        content=declaration + xml_bytes,
        media_type="application/xml",
        status_code=status_code
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schemas
    init_db()
    
    # Start consumer in a background daemon thread
    consumer_thread = threading.Thread(target=start_rabbitmq_consumer, daemon=True)
    consumer_thread.start()
    print("[Attendance] Background consumer thread started.")
    
    yield

app = FastAPI(
    title="Attendance System - API",
    description="Provides endpoints for recording and recapping student attendance (XML Output). Integrated with RabbitMQ.",
    version="1.0.0",
    lifespan=lifespan
)

class RecordAttendanceRequest(BaseModel):
    student_id: str
    class_id: str
    status: str  # present, absent, sick, permit

class ClassAttendanceRecord(BaseModel):
    student_id: str
    status: str  # present, excused, absent

class ClassAttendanceRequest(BaseModel):
    class_id: str
    records: list[ClassAttendanceRecord]
    attendance_date: str = None

class SessionRecord(BaseModel):
    student_id: str
    status: str  # present, excused, absent

class CreateSessionRequest(BaseModel):
    class_id: str
    meeting_number: int
    attendance_date: str
    records: list[SessionRecord]

# DB Helper to save session and details
def save_session_in_db(class_id: str, attendance_date: str, records: list, meeting_number: int = None) -> int:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        if not meeting_number:
            # Find existing session for class and date
            cursor.execute("SELECT id FROM attendance_sessions WHERE class_id = ? AND attendance_date = ?", (class_id, attendance_date))
            sess_row = cursor.fetchone()
            if sess_row:
                session_id = sess_row[0]
            else:
                # Count sessions to determine meeting number
                cursor.execute("SELECT COUNT(*) FROM attendance_sessions WHERE class_id = ?", (class_id,))
                meeting_number = cursor.fetchone()[0] + 1
                created_time = datetime.utcnow().isoformat() + "Z"
                cursor.execute("""
                    INSERT INTO attendance_sessions (class_id, meeting_number, attendance_date, created_at)
                    VALUES (?, ?, ?, ?)
                """, (class_id, meeting_number, attendance_date, created_time))
                session_id = cursor.lastrowid
        else:
            # Explicit session creation. Check if already exists for safety.
            cursor.execute("SELECT id FROM attendance_sessions WHERE class_id = ? AND meeting_number = ?", (class_id, meeting_number))
            sess_row = cursor.fetchone()
            if sess_row:
                session_id = sess_row[0]
            else:
                created_time = datetime.utcnow().isoformat() + "Z"
                cursor.execute("""
                    INSERT INTO attendance_sessions (class_id, meeting_number, attendance_date, created_at)
                    VALUES (?, ?, ?, ?)
                """, (class_id, meeting_number, attendance_date, created_time))
                session_id = cursor.lastrowid
            
        created_time = datetime.utcnow().isoformat() + "Z"
        for rec in records:
            student_id = rec.student_id if hasattr(rec, 'student_id') else rec.get('student_id')
            status = rec.status if hasattr(rec, 'status') else rec.get('status')
            
            # Check active student
            cursor.execute("SELECT is_active FROM students WHERE student_id = ?", (student_id,))
            row = cursor.fetchone()
            if not row or not row[0]:
                continue
                
            cursor.execute("""
                INSERT INTO attendance_details (session_id, student_id, status, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id, student_id) DO UPDATE SET status=excluded.status
            """, (session_id, student_id, status.lower(), created_time))
            
        conn.commit()
        conn.close()
        return session_id
    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

@app.get("/")
def read_root():
    # Even the root response is returned in XML to match constraints
    root = ET.Element("ServiceInfo")
    name = ET.SubElement(root, "name")
    name.text = "Attendance Service"
    status = ET.SubElement(root, "status")
    status.text = "Running"
    info = ET.SubElement(root, "info")
    info.text = "Exposes attendance recording and recap endpoints in XML format."
    return to_xml_response(root)

@app.get("/attendance/classes")
def get_classes():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT class_id, name FROM classes")
    rows = cursor.fetchall()
    conn.close()
    return [{"class_id": row[0], "name": row[1]} for row in rows]

@app.get("/attendance/classes/{id}/students")
def get_class_students(id: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.student_id, s.name FROM students s
        JOIN enrollments e ON s.student_id = e.student_id
        WHERE e.class_id = ? AND s.is_active = 1
    """, (id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"student_id": row[0], "name": row[1]} for row in rows]

@app.post("/attendance/session")
def create_attendance_session(request: CreateSessionRequest):
    try:
        session_id = save_session_in_db(
            class_id=request.class_id,
            attendance_date=request.attendance_date,
            records=request.records,
            meeting_number=request.meeting_number
        )
        root = ET.Element("SessionCreationResult")
        status_elem = ET.SubElement(root, "status")
        status_elem.text = "success"
        sess_id_elem = ET.SubElement(root, "session_id")
        sess_id_elem.text = str(session_id)
        msg_elem = ET.SubElement(root, "message")
        msg_elem.text = f"Attendance session {session_id} created successfully."
        return to_xml_response(root)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/attendance/classes/{class_id}/sessions")
def get_class_sessions(class_id: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.id, s.meeting_number, s.attendance_date, s.created_at,
               SUM(CASE WHEN d.status = 'present' THEN 1 ELSE 0 END) as present_count,
               SUM(CASE WHEN d.status = 'excused' THEN 1 ELSE 0 END) as excused_count,
               SUM(CASE WHEN d.status = 'absent' THEN 1 ELSE 0 END) as absent_count
        FROM attendance_sessions s
        LEFT JOIN attendance_details d ON s.id = d.session_id
        WHERE s.class_id = ?
        GROUP BY s.id
        ORDER BY s.meeting_number ASC
    """, (class_id,))
    rows = cursor.fetchall()
    conn.close()
    
    # Build XML response
    root = ET.Element("ClassSessionsHistory")
    c_id = ET.SubElement(root, "class_id")
    c_id.text = class_id
    total_sessions = ET.SubElement(root, "total_sessions")
    total_sessions.text = str(len(rows))
    
    sessions_list = ET.SubElement(root, "sessions")
    for row in rows:
        sess_elem = ET.SubElement(sessions_list, "session")
        s_id = ET.SubElement(sess_elem, "id")
        s_id.text = str(row[0])
        mtg_num = ET.SubElement(sess_elem, "meeting_number")
        mtg_num.text = str(row[1])
        att_date = ET.SubElement(sess_elem, "attendance_date")
        att_date.text = row[2]
        created_at = ET.SubElement(sess_elem, "created_at")
        created_at.text = row[3]
        
        counts = ET.SubElement(sess_elem, "counts")
        present = ET.SubElement(counts, "present")
        present.text = str(row[4])
        excused = ET.SubElement(counts, "excused")
        excused.text = str(row[5])
        absent = ET.SubElement(counts, "absent")
        absent.text = str(row[6])
        
    return to_xml_response(root)


@app.get("/attendance/classes/{class_id}/history")
def get_class_attendance_history(class_id: str):
    """
    Retrieves the full individual attendance logs for all sessions in a class and formats the output as XML.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.attendance_date, s.meeting_number, d.student_id, st.name, d.status, s.id
        FROM attendance_details d
        JOIN attendance_sessions s ON d.session_id = s.id
        JOIN students st ON d.student_id = st.student_id
        WHERE s.class_id = ?
        ORDER BY s.attendance_date DESC, s.meeting_number DESC, st.name ASC
    """, (class_id,))
    rows = cursor.fetchall()
    conn.close()
    
    # Build XML response
    root = ET.Element("ClassAttendanceHistory")
    c_id = ET.SubElement(root, "class_id")
    c_id.text = class_id
    total_records = ET.SubElement(root, "total_records")
    total_records.text = str(len(rows))
    
    records_list = ET.SubElement(root, "records")
    for row in rows:
        rec_elem = ET.SubElement(records_list, "record")
        att_date = ET.SubElement(rec_elem, "attendance_date")
        att_date.text = row[0]
        mtg_num = ET.SubElement(rec_elem, "meeting_number")
        mtg_num.text = str(row[1])
        student_id = ET.SubElement(rec_elem, "student_id")
        student_id.text = row[2]
        student_name = ET.SubElement(rec_elem, "student_name")
        student_name.text = row[3]
        status = ET.SubElement(rec_elem, "status")
        status.text = row[4]
        session_id = ET.SubElement(rec_elem, "session_id")
        session_id.text = str(row[5])
        
    return to_xml_response(root)


@app.get("/attendance/sessions/{session_id}")
def get_session_details(session_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Fetch session info
    cursor.execute("SELECT class_id, meeting_number, attendance_date FROM attendance_sessions WHERE id = ?", (session_id,))
    sess = cursor.fetchone()
    if not sess:
        conn.close()
        raise HTTPException(status_code=404, detail="Session not found")
        
    class_id, meeting_number, attendance_date = sess
    
    # Fetch detail list
    cursor.execute("""
        SELECT d.student_id, s.name, d.status
        FROM attendance_details d
        JOIN students s ON d.student_id = s.student_id
        WHERE d.session_id = ?
    """, (session_id,))
    rows = cursor.fetchall()
    conn.close()
    
    root = ET.Element("SessionDetails")
    s_id = ET.SubElement(root, "session_id")
    s_id.text = str(session_id)
    c_id = ET.SubElement(root, "class_id")
    c_id.text = class_id
    mtg_num = ET.SubElement(root, "meeting_number")
    mtg_num.text = str(meeting_number)
    att_date = ET.SubElement(root, "attendance_date")
    att_date.text = attendance_date
    
    records_list = ET.SubElement(root, "records")
    for row in rows:
        rec_elem = ET.SubElement(records_list, "record")
        std_id = ET.SubElement(rec_elem, "student_id")
        std_id.text = row[0]
        std_name = ET.SubElement(rec_elem, "student_name")
        std_name.text = row[1]
        status = ET.SubElement(rec_elem, "status")
        status.text = row[2]
        
    return to_xml_response(root)

@app.post("/attendance/record")
def record_attendance(request: Union[ClassAttendanceRequest, RecordAttendanceRequest]):
    if isinstance(request, ClassAttendanceRequest):
        attendance_date = request.attendance_date or datetime.utcnow().strftime("%Y-%m-%d")
        try:
            session_id = save_session_in_db(
                class_id=request.class_id,
                attendance_date=attendance_date,
                records=request.records
            )
            return {"status": "success", "message": f"Class attendance recorded in session {session_id}."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        # Check active student
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT is_active FROM students WHERE student_id = ?", (request.student_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row or not row[0]:
            root = ET.Element("AttendanceResult")
            status = ET.SubElement(root, "status")
            status.text = "error"
            message = ET.SubElement(root, "message")
            message.text = f"Access denied. Student {request.student_id} is inactive."
            return to_xml_response(root, status_code=403)
            
        attendance_date = datetime.utcnow().strftime("%Y-%m-%d")
        status_mapped = request.status.lower()
        if status_mapped in ('sick', 'permit'):
            status_mapped = 'excused'
            
        try:
            session_id = save_session_in_db(
                class_id=request.class_id,
                attendance_date=attendance_date,
                records=[{"student_id": request.student_id, "status": status_mapped}]
            )
            
            root = ET.Element("AttendanceResult")
            status = ET.SubElement(root, "status")
            status.text = "success"
            message = ET.SubElement(root, "message")
            message.text = "Attendance recorded successfully."
            
            record = ET.SubElement(root, "record")
            student = ET.SubElement(record, "student_id")
            student.text = request.student_id
            clazz = ET.SubElement(record, "class_id")
            clazz.text = request.class_id
            att_status = ET.SubElement(record, "status")
            att_status.text = request.status.lower()
            recorded_at = ET.SubElement(record, "recorded_at")
            recorded_at.text = datetime.utcnow().isoformat() + "Z"
            return to_xml_response(root)
        except Exception as e:
            root = ET.Element("AttendanceResult")
            status = ET.SubElement(root, "status")
            status.text = "error"
            message = ET.SubElement(root, "message")
            message.text = f"Error: {str(e)}"
            return to_xml_response(root, status_code=500)

@app.get("/attendance/recap/{student_id}")
def get_attendance_recap(student_id: str):
    """
    Retrieves the attendance logs for a student and formats the output as XML.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check current active status
    cursor.execute("SELECT name, is_active FROM students WHERE student_id = ?", (student_id,))
    row = cursor.fetchone()
    student_name = row[0] if row else "Unknown"
    is_active = bool(row[1]) if row else False
    
    # Retrieve logs
    cursor.execute("""
        SELECT d.id, s.class_id, d.status, s.attendance_date 
        FROM attendance_details d
        JOIN attendance_sessions s ON d.session_id = s.id
        WHERE d.student_id = ?
        ORDER BY s.attendance_date DESC
    """, (student_id,))
    logs = cursor.fetchall()
    conn.close()
    
    # Build XML Recap
    root = ET.Element("AttendanceRecap")
    student = ET.SubElement(root, "student_id")
    student.text = student_id
    s_name = ET.SubElement(root, "student_name")
    s_name.text = student_name
    active_status = ET.SubElement(root, "is_active")
    active_status.text = str(is_active).lower()
    total_records = ET.SubElement(root, "total_records")
    total_records.text = str(len(logs))
    
    records_list = ET.SubElement(root, "records")
    for log in logs:
        log_elem = ET.SubElement(records_list, "log")
        log_id = ET.SubElement(log_elem, "id")
        log_id.text = str(log[0])
        student_id_elem = ET.SubElement(log_elem, "student_id")
        student_id_elem.text = student_id
        student_name_elem = ET.SubElement(log_elem, "student_name")
        student_name_elem.text = student_name
        class_id = ET.SubElement(log_elem, "class_id")
        class_id.text = log[1]
        status = ET.SubElement(log_elem, "status")
        status.text = log[2]
        recorded_at = ET.SubElement(log_elem, "recorded_at")
        recorded_at.text = log[3]
        
    return to_xml_response(root)
