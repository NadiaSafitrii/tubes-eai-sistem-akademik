import os
import pika
import json

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'rabbitmq')

def route_message(ch, method, properties, body):
    try:
        # Parsing JSON internal (Canonical Data Model)
        message = json.loads(body)
        event_type = message.get("event_type")
        
        # Logika Content-Based Router
        if event_type == "student.registered":
            target_queues = ["student.registered"]
        elif event_type == "spp.created":
            target_queues = ["spp.created"]
        elif event_type == "spp.paid":
            target_queues = ["spp.paid", "siakad.spp.paid"]
        elif event_type == "student.active":
            target_queues = ["student.active", "siakad.student.active"]
        else:
            target_queues = ["dead.letter"] # Event tidak dikenali

        print(f"[Router] Merutekan event '{event_type}' ke antrean {target_queues}")

        # Teruskan pesan ke seluruh antrean target
        for target_queue in target_queues:
            ch.basic_publish(
                exchange='',
                routing_key=target_queue,
                body=body,
                properties=pika.BasicProperties(delivery_mode=2) # Persistent
            )
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        print(f"[Router Error] Gagal memproses pesan: {e}")
        # Lempar ke dead.letter jika terjadi kegagalan sistem
        ch.basic_publish(exchange='', routing_key='dead.letter', body=body)
        ch.basic_ack(delivery_tag=method.delivery_tag)

def start_router():
    connection = pika.BlockingConnection(pika.ConnectionParameters(RABBITMQ_HOST))
    channel = connection.channel()
    
    # Router mendengarkan dari antrean "incoming_events"
    channel.queue_declare(queue="incoming_events", durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue="incoming_events", on_message_callback=route_message)
    
    print("[Router] Menunggu pesan masuk di 'incoming_events'...")
    channel.start_consuming()

if __name__ == "__main__":
    start_router()