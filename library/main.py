import time
import threading
import json
import sqlite3
from datetime import datetime
import pika
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager

# Database configuration
DB_FILE = "library.db"

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
    # Create loans table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            book_id TEXT,
            book_title TEXT,
            borrowed_at TEXT,
            FOREIGN KEY(student_id) REFERENCES students(student_id)
        )
    """)
    conn.commit()
    conn.close()
    print("SQLite Database initialized successfully in Library service.")

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

def publish_student_active(student_id: str):
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT)
        )
        channel = connection.channel()
        channel.queue_declare(queue="incoming_events", durable=True)
        
        event = {
            "student_id": student_id,
            "event_type": "student.active",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "payload": {
                "activated_at": datetime.utcnow().isoformat() + "Z"
            }
        }
        
        channel.basic_publish(
            exchange="",
            routing_key="incoming_events",
            body=json.dumps(event),
            properties=pika.BasicProperties(
                delivery_mode=2  # Make message persistent
            )
        )
        connection.close()
        print(f"[Library] Successfully published event 'student.active' for student: {student_id}")
    except Exception as e:
        print(f"[Library] Error publishing student.active event: {e}")

def start_rabbitmq_consumer():
    try:
        connection = connect_rabbitmq()
        channel = connection.channel()
        
        # Declare the spp.paid queue (must be durable)
        channel.queue_declare(queue="spp.paid", durable=True)
        
        def callback(ch, method, properties, body):
            try:
                print(f"[Library] Received raw queue body: {body.decode()}")
                data = json.loads(body.decode())
                
                # Check structure of the canonical format
                student_id = data.get("student_id")
                event_type = data.get("event_type")
                
                print(f"[Library] Processing event '{event_type}' for student: {student_id}")
                
                if student_id:
                    # Update local SQLite database
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO students (student_id, is_active, updated_at)
                        VALUES (?, 1, ?)
                        ON CONFLICT(student_id) DO UPDATE SET is_active=1, updated_at=?
                    """, (student_id, datetime.utcnow().isoformat() + "Z", datetime.utcnow().isoformat() + "Z"))
                    conn.commit()
                    conn.close()
                    print(f"[Library] Student {student_id} access rights REACTIVATED (SPP Paid).")
                    
                    # Publish event student.active to notify next systems (e.g. Attendance)
                    publish_student_active(student_id)
                
                ch.basic_ack(delivery_tag=method.delivery_tag)
                print(f"[Library] Acknowledged message.")
            except Exception as e:
                print(f"[Library] Error inside consumer callback: {e}")
                # Reject message without requeueing to avoid infinite loop
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        # Set QoS prefetch count to 1
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue="spp.paid", on_message_callback=callback)
        print("[Library] RabbitMQ consumer listening on 'spp.paid' queue...")
        channel.start_consuming()
    except Exception as e:
        print(f"[Library] RabbitMQ consumer main runner error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schemas
    init_db()
    
    # Start consumer in a background daemon thread
    consumer_thread = threading.Thread(target=start_rabbitmq_consumer, daemon=True)
    consumer_thread.start()
    print("[Library] Background consumer thread started.")
    
    yield
    # Shutdown steps if needed

app = FastAPI(
    title="Library Management System - API",
    description="Provides endpoints for library access verification and book borrowing (REST / JSON). Integrated with RabbitMQ.",
    version="1.0.0",
    lifespan=lifespan
)

class BorrowRequest(BaseModel):
    student_id: str
    book_id: str
    book_title: str

@app.get("/")
def read_root():
    return {
        "service": "Library Service",
        "status": "Running",
        "info": "Exposes status endpoints and book borrowing operations."
    }

@app.get("/library/status/{student_id}")
def get_library_status(student_id: str):
    """
    Get access status of a student to the library.
    Checks if student has paid SPP and is active.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT is_active, updated_at FROM students WHERE student_id = ?", (student_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return {
            "student_id": student_id,
            "is_active": False,
            "reason": "Access denied. Student is not registered or has unpaid SPP.",
            "updated_at": None
        }
    
    is_active = bool(row[0])
    return {
        "student_id": student_id,
        "is_active": is_active,
        "reason": "Access active. Book borrowing allowed." if is_active else "Access suspended. SPP unpaid.",
        "updated_at": row[1]
    }

@app.post("/library/borrow")
def borrow_book(request: BorrowRequest):
    """
    Borrow a book from the library.
    Checks if the student's status is active.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check status
    cursor.execute("SELECT is_active FROM students WHERE student_id = ?", (request.student_id,))
    row = cursor.fetchone()
    
    if not row or not row[0]:
        conn.close()
        raise HTTPException(
            status_code=403,
            detail={
                "error": "Forbidden",
                "message": f"Student {request.student_id} is not active in Library. Cannot borrow books."
            }
        )
    
    # Record loan
    borrow_time = datetime.utcnow().isoformat() + "Z"
    cursor.execute(
        "INSERT INTO loans (student_id, book_id, book_title, borrowed_at) VALUES (?, ?, ?, ?)",
        (request.student_id, request.book_id, request.book_title, borrow_time)
    )
    conn.commit()
    conn.close()
    
    return {
        "message": "Book borrowed successfully.",
        "student_id": request.student_id,
        "book_id": request.book_id,
        "book_title": request.book_title,
        "borrowed_at": borrow_time
    }

@app.get("/library/loans/{student_id}")
def get_loans(student_id: str):
    """
    List all books borrowed by a specific student.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT book_id, book_title, borrowed_at FROM loans WHERE student_id = ?", (student_id,))
    rows = cursor.fetchall()
    conn.close()
    
    loans = [
        {"book_id": row[0], "book_title": row[1], "borrowed_at": row[2]}
        for row in rows
    ]
    return {
        "student_id": student_id,
        "loans_count": len(loans),
        "loans": loans
    }
