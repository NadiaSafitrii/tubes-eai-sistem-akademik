import os
import json
import pika
import requests
from transformers.converter import csv_to_cdm

def fetch_and_publish_keuangan():
    finance_url = "http://finance:8002/bills"
    
    try:
        # 1. Adapter mengambil data dalam format aslinya (CSV)
        response = requests.get(finance_url)
        
        if response.status_code == 200:
            csv_data = response.text
            
            # 2. Transformer mengubah ke JSON (CDM)
            cdm_json_list = json.loads(csv_to_cdm(csv_data))
            
            # Gunakan RABBITMQ_HOST dari environment
            rabbitmq_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
            connection = pika.BlockingConnection(pika.ConnectionParameters(rabbitmq_host))
            channel = connection.channel()
            
            # Deklarasi antrean masuk agar aman jika belum dibuat
            channel.queue_declare(queue="incoming_events", durable=True)
            
            # 3. Adapter mengirimkan ke Router
            for cdm_msg in cdm_json_list:
                channel.basic_publish(
                    exchange='',
                    routing_key='incoming_events',
                    body=json.dumps(cdm_msg),
                    properties=pika.BasicProperties(delivery_mode=2)
                )
                print(f"[Adapter Keuangan] Berhasil meneruskan data SPP untuk {cdm_msg['student_id']}")
                
            connection.close()
        else:
            print(f"[Adapter Keuangan] Gagal mengambil data. Status code: {response.status_code}")
            
    except Exception as e:
        print(f"[Adapter Keuangan] Terjadi error: {e}")

if __name__ == "__main__":
    fetch_and_publish_keuangan()