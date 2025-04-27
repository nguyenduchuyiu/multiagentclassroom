import time
import uuid

def get_timestamp():
    return int(time.time() * 1000)

def generate_uuid():
    return str(uuid.uuid4())