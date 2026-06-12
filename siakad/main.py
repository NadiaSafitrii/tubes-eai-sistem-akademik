# SIAKAD Main Application
import os
import json
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import aio_pika
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database import engine, Base, get_db, SessionLocal
import models

# Automatically create database tables if they do not exist
Base.metadata.create_all(bind=engine)

async def consume_student_active(connection: aio_pika.RobustConnection):
    try:
        channel = await connection.channel()
        queue = await channel.declare_queue("siakad.student.active", durable=True)
        
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        event_data = json.loads(message.body.decode())
                        print(f"[SIAKAD Consumer] Received student.active event: {event_data}")
                        
                        student_id = event_data.get("student_id") or event_data.get("payload", {}).get("student_id")
                        
                        db = SessionLocal()
                        try:
                            db_student = db.query(models.Student).filter(models.Student.student_id == student_id).first()
                            if db_student:
                                db_student.status = "active"
                                db.commit()
                                print(f"[SIAKAD Consumer] Successfully activated student {student_id} in SIAKAD database.")
                            else:
                                logging.warning(f"[SIAKAD Consumer] Student {student_id} not found in SIAKAD database.")
                        finally:
                            db.close()
                            
                    except Exception as ex:
                        print(f"[SIAKAD Consumer Error] Failed to process message: {str(ex)}")
    except Exception as e:
        print(f"[SIAKAD Consumer Error] Connection/channel error: {str(e)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup RabbitMQ connection details
    rabbitmq_url = getattr(app.state, "rabbitmq_url", None)
    if not rabbitmq_url:
        rabbitmq_host = os.getenv("RABBITMQ_HOST", "rabbitmq")
        rabbitmq_port = int(os.getenv("RABBITMQ_PORT", "5672"))
        rabbitmq_user = os.getenv("RABBITMQ_USER", "guest")
        rabbitmq_password = os.getenv("RABBITMQ_PASSWORD", "guest")
        rabbitmq_url = f"amqp://{rabbitmq_user}:{rabbitmq_password}@{rabbitmq_host}:{rabbitmq_port}/"
        app.state.rabbitmq_url = rabbitmq_url
    
    # Establish persistent dynamic async connection at startup with retry logic
    import asyncio
    retries = 12
    rabbitmq_connection = None
    while retries > 0:
        try:
            rabbitmq_connection = await aio_pika.connect_robust(app.state.rabbitmq_url)
            break
        except Exception as e:
            print(f"[SIAKAD Startup] RabbitMQ not ready ({e}). Retrying in 5 seconds...")
            await asyncio.sleep(5)
            retries -= 1
            
    if not rabbitmq_connection:
        raise RuntimeError("Failed to connect to RabbitMQ after multiple attempts.")
        
    app.state.rabbitmq_connection = rabbitmq_connection
    
    # Start RabbitMQ consumer for student.active in the background
    asyncio.create_task(consume_student_active(rabbitmq_connection))
    
    # Seed default classes
    db = SessionLocal()
    try:
        default_classes = [
            {"class_id": "EAI-A", "name": "Enterprise Application Integration"},
            {"class_id": "BPM-A", "name": "Business Process Management"},
            {"class_id": "IF-44-01", "name": "Informatika 44-01"}
        ]
        for c in default_classes:
            existing = db.query(models.Class).filter(models.Class.class_id == c["class_id"]).first()
            if not existing:
                db_class = models.Class(class_id=c["class_id"], name=c["name"])
                db.add(db_class)
        db.commit()
        print("[SIAKAD Startup] Seeded default classes successfully.")
    except Exception as e:
        print(f"[SIAKAD Startup] Failed to seed default classes: {e}")
    finally:
        db.close()

    yield
    # Close connection on shutdown
    await rabbitmq_connection.close()

app = FastAPI(
    title="SIAKAD Academic Service",
    description="Service managing students and handling student re-registration events.",
    version="1.0.0",
    lifespan=lifespan
)

# Pydantic Schemas
class StudentCreate(BaseModel):
    student_id: str
    name: str
    email: EmailStr
    semester: int

class ClassInfo(BaseModel):
    id: str
    name: str

class StudentResponse(BaseModel):
    student_id: str
    name: str
    email: str
    semester: int
    status: str
    classes: list[ClassInfo] = []

    model_config = {
        "from_attributes": True
    }

class EnrollRequest(BaseModel):
    class_id: str = None
    class_ids: list[str] = None


# RabbitMQ Helper
async def publish_event(queue_name: str, message_body: dict, connection: aio_pika.RobustConnection):
    try:
        # Reuse persistent connection to open a temporary channel
        async with connection.channel() as channel:
            # Declare the queue (durable to match RabbitMQ configuration best practices)
            await channel.declare_queue(queue_name, durable=True)
            # Publish to the default exchange with queue_name as the routing key
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(message_body).encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT
                ),
                routing_key=queue_name
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish event to message broker: {str(e)}"
        )

# Helper to get enrolled classes
def get_enrolled_classes(student_id: str, db: Session) -> list:
    enrollments = db.query(models.Enrollment).filter(models.Enrollment.student_id == student_id).all()
    classes_info = []
    for e in enrollments:
        cls = db.query(models.Class).filter(models.Class.class_id == e.class_id).first()
        if cls:
            classes_info.append({"id": cls.class_id, "name": cls.name})
    return classes_info

# API Endpoints
@app.post("/students", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
async def create_student(student: StudentCreate, db: Session = Depends(get_db)):
    from anyio import to_thread
    
    def db_operations():
        # Check if student_id already exists
        existing_id = db.query(models.Student).filter(models.Student.student_id == student.student_id).first()
        if existing_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Student with this ID already exists"
            )
        
        # Check if email already exists
        existing_email = db.query(models.Student).filter(models.Student.email == student.email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Student with this email already exists"
            )
        
        db_student = models.Student(
            student_id=student.student_id,
            name=student.name,
            email=student.email,
            semester=student.semester,
            status="inactive" # default value
        )
        db.add(db_student)
        db.commit()
        db.refresh(db_student)
        return db_student

    try:
        db_student = await to_thread.run_sync(db_operations)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database transaction failed: {str(e)}"
        )
    
    classes_info = get_enrolled_classes(db_student.student_id, db)
    
    # Construct Canonical Data Model (CDM) message
    cdm_message = {
        "student_id": db_student.student_id,
        "event_type": "student.registered",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "student_id": db_student.student_id,
            "name": db_student.name,
            "email": db_student.email,
            "semester": db_student.semester,
            "status": db_student.status,
            "classes": classes_info
        }
    }
    
    # Get RabbitMQ connection from application state
    rabbitmq_connection = app.state.rabbitmq_connection
    
    # Publish event via reusable persistent connection
    await publish_event("student.registered", cdm_message, rabbitmq_connection)
    
    db_student.classes = classes_info
    return db_student

@app.get("/students/{id}", response_model=StudentResponse)
def get_student(id: str, db: Session = Depends(get_db)):
    db_student = db.query(models.Student).filter(models.Student.student_id == id).first()
    if not db_student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {id} not found"
        )
    db_student.classes = get_enrolled_classes(db_student.student_id, db)
    return db_student

@app.post("/students/{id}/register")
async def register_student(id: str, db: Session = Depends(get_db)):
    from anyio import to_thread
    
    def get_and_update_student():
        db_student = db.query(models.Student).filter(models.Student.student_id == id).first()
        if not db_student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Student with ID {id} not found"
            )
        
        # Check if they have already paid SPP in Keuangan
        is_paid = False
        try:
            import urllib.request
            import json
            finance_url = "http://finance:8002/bills-json"
            req = urllib.request.Request(finance_url)
            with urllib.request.urlopen(req, timeout=3) as response:
                bills = json.loads(response.read().decode())
                for bill in bills:
                    if str(bill.get("student_id")) == str(id) and bill.get("semester") == db_student.semester:
                        if bill.get("status") == "paid":
                            is_paid = True
                            break
        except Exception as e:
            print(f"[SIAKAD Register] Failed to check bill status from Finance: {e}")

        # Set status based on payment check
        if is_paid:
            db_student.status = "active"
        else:
            db_student.status = "inactive"
            
        db.commit()
        db.refresh(db_student)
        return db_student, is_paid

    try:
        # Offload blocking database transaction to a thread worker
        db_student, is_paid = await to_thread.run_sync(get_and_update_student)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database transaction failed: {str(e)}"
        )
    
    classes_info = get_enrolled_classes(db_student.student_id, db)
    
    # If the student is active, publish student.active event instead of student.registered to sync enrollment immediately
    event_type = "student.active" if is_paid else "student.registered"
    routing_key = "incoming_events" if is_paid else "student.registered"
    
    # Construct Canonical Data Model (CDM) message
    cdm_message = {
        "student_id": db_student.student_id,
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "student_id": db_student.student_id,
            "name": db_student.name,
            "email": db_student.email,
            "semester": db_student.semester,
            "status": db_student.status,
            "classes": classes_info,
            "activated_at": datetime.now(timezone.utc).isoformat() if is_paid else None
        }
    }
    
    # Get RabbitMQ connection from application state
    rabbitmq_connection = app.state.rabbitmq_connection
    
    # Publish event via reusable persistent connection
    await publish_event(routing_key, cdm_message, rabbitmq_connection)
    
    return {
        "status": "success",
        "message": f"Student successfully registered (status: {db_student.status}) and event published to RabbitMQ",
        "data": {
            "student_id": db_student.student_id,
            "status": db_student.status
        }
    }

@app.get("/students", response_model=list[StudentResponse])
def list_students(db: Session = Depends(get_db)):
    """
    Retrieve all students registered in SIAKAD database.
    """
    students = db.query(models.Student).all()
    for s in students:
        s.classes = get_enrolled_classes(s.student_id, db)
    return students

@app.post("/students/{student_id}/enroll")
async def enroll_student(student_id: str, request: EnrollRequest, db: Session = Depends(get_db)):
    student = db.query(models.Student).filter(models.Student.student_id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {student_id} not found"
        )
    
    class_ids = request.class_ids or []
    if request.class_id:
        class_ids.append(request.class_id)
        
    # Clear existing enrollments to allow complete updates
    db.query(models.Enrollment).filter(models.Enrollment.student_id == student_id).delete()
    
    for cid in class_ids:
        # Check if class exists, if not seed it or error
        cls = db.query(models.Class).filter(models.Class.class_id == cid).first()
        if not cls:
            # Seed automatically to avoid strict erroring
            cls = models.Class(class_id=cid, name=cid)
            db.add(cls)
            db.commit()
            
        enrollment = models.Enrollment(student_id=student_id, class_id=cid)
        db.add(enrollment)
        
    db.commit()
    
    # Check if student is active OR check if they have paid in Keuangan to self-heal their active status
    is_active = (student.status == "active")
    if not is_active:
        try:
            import urllib.request
            import json
            finance_url = "http://finance:8002/bills-json"
            req = urllib.request.Request(finance_url)
            with urllib.request.urlopen(req, timeout=3) as response:
                bills = json.loads(response.read().decode())
                for bill in bills:
                    if str(bill.get("student_id")) == str(student_id) and bill.get("semester") == student.semester:
                        if bill.get("status") == "paid":
                            is_active = True
                            student.status = "active"
                            db.commit()
                            print(f"[SIAKAD Enroll] Self-healed student {student_id} status to active based on paid bill.")
                            break
        except Exception as e:
            print(f"[SIAKAD Enroll] Failed to check bill status from Finance: {e}")
            
    # If student is active (or newly activated), publish student.active event to sync enrollment immediately
    if is_active:
        classes_info = get_enrolled_classes(student_id, db)
        cdm_message = {
            "student_id": student_id,
            "event_type": "student.active",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "student_id": student_id,
                "name": student.name,
                "status": "active",
                "classes": classes_info,
                "activated_at": datetime.now(timezone.utc).isoformat()
            }
        }
        rabbitmq_connection = app.state.rabbitmq_connection
        try:
            await publish_event("incoming_events", cdm_message, rabbitmq_connection)
            print(f"[SIAKAD] Student {student_id} is active. Published student.active event to sync enrollment.")
        except Exception as e:
            print(f"[SIAKAD Error] Failed to publish sync event: {e}")
            
    return {"status": "success", "message": f"Student {student_id} successfully enrolled in classes."}

@app.get("/classes")
def list_classes(db: Session = Depends(get_db)):
    return db.query(models.Class).all()

@app.get("/status")
def get_status():
    """
    Healthcheck endpoint for monitoring.
    """
    return {
        "status": "online",
        "service": "SIAKAD Academic Service"
    }
