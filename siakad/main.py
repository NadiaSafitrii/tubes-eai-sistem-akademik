import json
import time
from datetime import datetime
import pika
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="SIAKAD (Academic System) - Skeleton API",
    description="Person 1 Skeleton. Used to trigger student registration events.",
    version="1.0.0"
)

# RabbitMQ configuration
RABBITMQ_HOST = "rabbitmq"
RABBITMQ_PORT = 5672

class RegisterRequest(BaseModel):
    student_id: str
    name: str
    email: str

def publish_event(queue_name: str, event: dict):
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT)
        )
        channel = connection.channel()
        channel.queue_declare(queue=queue_name, durable=True)
        
        channel.basic_publish(
            exchange="",
            routing_key=queue_name,
            body=json.dumps(event),
            properties=pika.BasicProperties(
                delivery_mode=2  # Persistent
            )
        )
        connection.close()
        return True
    except Exception as e:
        print(f"[SIAKAD] Event publication failed: {e}")
        return False

@app.get("/")
def read_root():
    return {
        "service": "SIAKAD Service (Academic)",
        "status": "Running Skeleton",
        "endpoints": {
            "register": "POST /siakad/register"
        }
    }

@app.post("/siakad/register")
def register_student(request: RegisterRequest):
    """
    Simulates a student registration in SIAKAD and publishes the student.registered event.
    """
    event = {
        "student_id": request.student_id,
        "event_type": "student.registered",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "payload": {
            "name": request.name,
            "email": request.email,
            "registered_at": datetime.utcnow().isoformat() + "Z"
        }
    }
    
    success = publish_event("student.registered", event)
    
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to publish registration event to RabbitMQ."
        )
        
    return {
        "message": "Student registration simulated successfully.",
        "student_id": request.student_id,
        "event_published": "student.registered"
    }
