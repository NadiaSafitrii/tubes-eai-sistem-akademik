import os
import json
import csv
import io
from datetime import datetime, timezone
from contextlib import asynccontextmanager

import aio_pika
from fastapi import FastAPI, Depends, HTTPException, status, Response
from pydantic import BaseModel
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
    title="Keuangan SPP Service",
    description="Service managing tuition bills and handling tuition payment events.",
    version="1.0.0",
    lifespan=lifespan
)

# Pydantic Schemas
class BillCreate(BaseModel):
    bill_id: str
    student_id: str
    amount: float
    semester: int

class BillResponse(BaseModel):
    bill_id: str
    student_id: str
    amount: float
    semester: int
    status: str
    created_at: datetime

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
@app.post("/bills", response_model=BillResponse, status_code=status.HTTP_201_CREATED)
def create_bill(bill: BillCreate, db: Session = Depends(get_db)):
    # Check if bill_id already exists
    existing_bill = db.query(models.Bill).filter(models.Bill.bill_id == bill.bill_id).first()
    if existing_bill:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bill with this ID already exists"
        )
    
    db_bill = models.Bill(
        bill_id=bill.bill_id,
        student_id=bill.student_id,
        amount=bill.amount,
        semester=bill.semester,
        status="unpaid" # default value
    )
    db.add(db_bill)
    db.commit()
    db.refresh(db_bill)
    return db_bill

@app.get("/bills")
def list_bills(db: Session = Depends(get_db)):
    bills = db.query(models.Bill).all()
    
    # Generate CSV response
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write CSV Header
    writer.writerow(["bill_id", "student_id", "amount", "semester", "status", "created_at"])
    
    # Write CSV Rows
    for bill in bills:
        writer.writerow([
            bill.bill_id,
            bill.student_id,
            bill.amount,
            bill.semester,
            bill.status,
            bill.created_at.isoformat() if bill.created_at else ""
        ])
    
    csv_data = output.getvalue()
    output.close()
    
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=bills.csv"
        }
    )

@app.post("/bills/{id}/pay")
async def pay_bill(id: str, db: Session = Depends(get_db)):
    from anyio import to_thread
    
    def get_and_update_bill():
        db_bill = db.query(models.Bill).filter(models.Bill.bill_id == id).first()
        if not db_bill:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Bill with ID {id} not found"
            )
        
        # Update status to paid
        db_bill.status = "paid"
        db.commit()
        db.refresh(db_bill)
        return db_bill

    try:
        # Offload blocking database transaction to a thread worker
        db_bill = await to_thread.run_sync(get_and_update_bill)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database transaction failed: {str(e)}"
        )
    
    # Construct Canonical Data Model (CDM) message
    cdm_message = {
        "student_id": db_bill.student_id,
        "event_type": "spp.paid",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "bill_id": db_bill.bill_id,
            "student_id": db_bill.student_id,
            "amount": db_bill.amount,
            "semester": db_bill.semester,
            "status": db_bill.status,
            "created_at": db_bill.created_at.isoformat() if db_bill.created_at else ""
        }
    }
    
    # Get RabbitMQ connection from application state
    rabbitmq_connection = app.state.rabbitmq_connection
    
    # Publish event via reusable persistent connection
    await publish_event("spp.paid", cdm_message, rabbitmq_connection)
    
    return {
        "status": "success",
        "message": "Bill successfully paid and event published to RabbitMQ",
        "data": {
            "bill_id": db_bill.bill_id,
            "status": db_bill.status
        }
    }
