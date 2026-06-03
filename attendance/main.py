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

# Database configuration
DB_FILE = "attendance.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Create students table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            is_active INTEGER DEFAULT 0,
            updated_at TEXT
        )
    """)
    # Create attendance_logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            class_id TEXT,
            status TEXT,
            recorded_at TEXT,
            FOREIGN KEY(student_id) REFERENCES students(student_id)
        )
    """)
    conn.commit()
    conn.close()
    print("SQLite Database initialized successfully in Attendance service.")

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
                    # Update local SQLite database to mark student as active
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO students (student_id, is_active, updated_at)
                        VALUES (?, 1, ?)
                        ON CONFLICT(student_id) DO UPDATE SET is_active=1, updated_at=?
                    """, (student_id, datetime.utcnow().isoformat() + "Z", datetime.utcnow().isoformat() + "Z"))
                    conn.commit()
                    conn.close()
                    print(f"[Attendance] Student {student_id} marked as ACTIVE. Ready to record attendance.")
                
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

@app.post("/attendance/record")
def record_attendance(request: RecordAttendanceRequest):
    """
    Records student attendance. Checks if student is active.
    Returns XML response.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check if student is active in local database
    cursor.execute("SELECT is_active FROM students WHERE student_id = ?", (request.student_id,))
    row = cursor.fetchone()
    
    # Check if student is active (row[0] == 1)
    if not row or not row[0]:
        conn.close()
        # Create XML error element
        root = ET.Element("AttendanceResult")
        status = ET.SubElement(root, "status")
        status.text = "error"
        message = ET.SubElement(root, "message")
        message.text = f"Access denied. Student {request.student_id} is inactive (SPP unpaid or unregistered)."
        return to_xml_response(root, status_code=403)
        
    # Record attendance log
    record_time = datetime.utcnow().isoformat() + "Z"
    cursor.execute(
        "INSERT INTO attendance_logs (student_id, class_id, status, recorded_at) VALUES (?, ?, ?, ?)",
        (request.student_id, request.class_id, request.status.lower(), record_time)
    )
    conn.commit()
    conn.close()
    
    # Build success XML
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
    recorded_at.text = record_time
    
    return to_xml_response(root)

@app.get("/attendance/recap/{student_id}")
def get_attendance_recap(student_id: str):
    """
    Retrieves the attendance logs for a student and formats the output as XML.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check current active status
    cursor.execute("SELECT is_active FROM students WHERE student_id = ?", (student_id,))
    row = cursor.fetchone()
    is_active = bool(row[0]) if row else False
    
    # Retrieve logs
    cursor.execute("SELECT id, class_id, status, recorded_at FROM attendance_logs WHERE student_id = ?", (student_id,))
    logs = cursor.fetchall()
    conn.close()
    
    # Build XML Recap
    root = ET.Element("AttendanceRecap")
    student = ET.SubElement(root, "student_id")
    student.text = student_id
    active_status = ET.SubElement(root, "is_active")
    active_status.text = str(is_active).lower()
    total_records = ET.SubElement(root, "total_records")
    total_records.text = str(len(logs))
    
    records_list = ET.SubElement(root, "records")
    for log in logs:
        log_elem = ET.SubElement(records_list, "log")
        log_id = ET.SubElement(log_elem, "id")
        log_id.text = str(log[0])
        class_id = ET.SubElement(log_elem, "class_id")
        class_id.text = log[1]
        status = ET.SubElement(log_elem, "status")
        status.text = log[2]
        recorded_at = ET.SubElement(log_elem, "recorded_at")
        recorded_at.text = log[3]
        
    return to_xml_response(root)
