import json
import time
from datetime import datetime
import pika
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="Finance System - Skeleton API",
    description="Person 2 Skeleton. Used to trigger SPP payment events.",
    version="1.0.0"
)

# RabbitMQ configuration
RABBITMQ_HOST = "rabbitmq"
RABBITMQ_PORT = 5672

class PaySppRequest(BaseModel):
    student_id: str
    amount: float

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
        print(f"[Finance] Event publication failed: {e}")
        return False

@app.get("/")
def read_root():
    return {
        "service": "Finance Service (SPP & Payments)",
        "status": "Running Skeleton",
        "endpoints": {
            "pay_spp": "POST /finance/pay-spp"
        }
    }

@app.post("/finance/pay-spp")
def pay_spp(request: PaySppRequest):
    """
    Simulates a payment of SPP tuition fee, publishing the spp.paid event.
    """
    event = {
        "student_id": request.student_id,
        "event_type": "spp.paid",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "payload": {
            "amount": request.amount,
            "paid_at": datetime.utcnow().isoformat() + "Z"
        }
    }
    
    success = publish_event("spp.paid", event)
    
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to publish spp.paid event to RabbitMQ."
        )
        
    return {
        "message": "SPP Tuition Payment simulated successfully.",
        "student_id": request.student_id,
        "amount": request.amount,
        "event_published": "spp.paid"
    }
