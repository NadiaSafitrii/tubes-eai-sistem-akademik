# SIAKAD Main Application
import os
import json
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import aio_pika
from fastapi import FastAPI, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from database import engine, Base, get_db
import models

# Automatically create database tables if they do not exist
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup RabbitMQ connection details from environment variables
    rabbitmq_host = os.getenv("RABBITMQ_HOST", "rabbitmq")
    rabbitmq_port = int(os.getenv("RABBITMQ_PORT", "5672"))
    rabbitmq_user = os.getenv("RABBITMQ_USER", "guest")
    rabbitmq_password = os.getenv("RABBITMQ_PASSWORD", "guest")
    
    rabbitmq_url = f"amqp://{rabbitmq_user}:{rabbitmq_password}@{rabbitmq_host}:{rabbitmq_port}/"
    
    # Establish persistent dynamic async connection at startup
    rabbitmq_connection = await aio_pika.connect_robust(rabbitmq_url)
    app.state.rabbitmq_connection = rabbitmq_connection
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

class StudentResponse(BaseModel):
    student_id: str
    name: str
    email: str
    semester: int
    status: str

    model_config = {
        "from_attributes": True
    }

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

# API Endpoints
@app.post("/students", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
def create_student(student: StudentCreate, db: Session = Depends(get_db)):
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

@app.get("/students/{id}", response_model=StudentResponse)
def get_student(id: str, db: Session = Depends(get_db)):
    db_student = db.query(models.Student).filter(models.Student.student_id == id).first()
    if not db_student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID {id} not found"
        )
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
        
        # Update student status to active
        db_student.status = "active"
        db.commit()
        db.refresh(db_student)
        return db_student

    try:
        # Offload blocking database transaction to a thread worker
        db_student = await to_thread.run_sync(get_and_update_student)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database transaction failed: {str(e)}"
        )
    
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
            "status": db_student.status
        }
    }
    
    # Get RabbitMQ connection from application state
    rabbitmq_connection = app.state.rabbitmq_connection
    
    # Publish event via reusable persistent connection
    await publish_event("student.registered", cdm_message, rabbitmq_connection)
    
    return {
        "status": "success",
        "message": "Student successfully registered and event published to RabbitMQ",
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
    return db.query(models.Student).all()

@app.get("/status")
def get_status():
    """
    Healthcheck endpoint for monitoring.
    """
    return {
        "status": "online",
        "service": "SIAKAD Academic Service"
    }
