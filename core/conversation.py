# conversation.py
import time
import uuid
import threading
from utils.helpers import get_timestamp # Giả sử có hàm này trong utils

class Conversation:
    def __init__(self):
        self._log = []
        self._lock = threading.Lock() # Đảm bảo thread-safe

    def add_message(self, sender, text):
        message = {
            "id": str(uuid.uuid4()),
            "sender": sender,
            "text": text,
            "timestamp": get_timestamp()
        }
        with self._lock:
            self._log.append(message)
            print(f"CONV LOG: {sender}: {text}")
        return message # Trả về để có thể broadcast ngay

    def get_history(self):
        with self._lock:
            return list(self._log) # Trả về bản sao

    def get_recent_history(self, count=10):
        with self._lock:
            return list(self._log[-count:])