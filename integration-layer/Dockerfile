FROM python:3.10-slim

WORKDIR /app

RUN pip install --no-cache-dir pika requests

COPY . .

CMD python setup_rabbitmq.py && python router/cbr.py