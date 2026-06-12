import os
import time
import pika

def setup_queues():
    rabbitmq_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
    
    retries = 20
    connection = None
    while retries > 0:
        try:
            print("Setup-RabbitMQ: Connecting to RabbitMQ...")
            connection = pika.BlockingConnection(pika.ConnectionParameters(rabbitmq_host))
            break
        except pika.exceptions.AMQPConnectionError as e:
            print(f"Setup-RabbitMQ: RabbitMQ not ready ({e}). Retrying in 5 seconds...")
            time.sleep(5)
            retries -= 1
            
    if not connection:
        raise Exception("Setup-RabbitMQ: Could not connect to RabbitMQ after multiple attempts.")
    
    channel = connection.channel()

    queues = [
        "incoming_events",     
        "student.registered",
        "spp.created",
        "spp.paid",
        "siakad.spp.paid",
        "student.active",
        "siakad.student.active",
        "dead.letter"
    ]

    for q in queues:
        channel.queue_declare(queue=q, durable=True)
        print(f"Queue '{q}' berhasil dibuat.")

    connection.close()

if __name__ == "__main__":
    setup_queues()