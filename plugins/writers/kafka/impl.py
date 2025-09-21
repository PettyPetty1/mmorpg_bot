
from __future__ import annotations
import os, json
try:
    from confluent_kafka import Producer
except Exception:
    Producer = None  # Allow import without kafka installed

class KafkaEventWriter:
    def __init__(self, topic: str | None = None, conf: dict | None = None):
        self.topic = topic or os.getenv("CONANBOT_KAFKA_TOPIC", "conanbot.events")
        self.conf = conf or {
            "bootstrap.servers": os.getenv("CONANBOT_KAFKA_BOOTSTRAP", "localhost:9092")
        }
        self.producer = Producer(self.conf) if Producer else None

    def open(self, path):
        # no-op; Kafka doesn't need a path
        pass

    def write(self, event):
        if not self.producer:
            return  # gracefully no-op if confluent_kafka missing
        payload = event.model_dump_json()
        self.producer.produce(self.topic, payload.encode("utf-8"))

    def close(self):
        if self.producer:
            self.producer.flush(5)
