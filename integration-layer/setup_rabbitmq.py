import os
import pika

def setup_queues():
    rabbitmq_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
    connection = pika.BlockingConnection(pika.ConnectionParameters(rabbitmq_host))
    
    channel = connection.channel()

    queues = [
        "incoming_events",     
        "student.registered",
        "spp.created",
        "spp.paid",
        "student.active",
        "dead.letter"
    ]

    for q in queues:
        channel.queue_declare(queue=q, durable=True)
        print(f"Queue '{q}' berhasil dibuat.")

    connection.close()

if __name__ == "__main__":
    setup_queues()