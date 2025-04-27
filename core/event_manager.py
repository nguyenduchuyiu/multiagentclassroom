# event_manager.py
import queue
import threading
import json

class EventManager:
    def __init__(self):
        self._sse_queues = {} # { client_id: queue.Queue() }
        self._lock = threading.Lock()

    def add_sse_client(self, client_id):
        q = queue.Queue()
        with self._lock:
            self._sse_queues[client_id] = q
        return q # Trả về queue cho route /stream

    def remove_sse_client(self, client_id):
        with self._lock:
            if client_id in self._sse_queues:
                # Gửi tín hiệu None để dừng generator của client đó (nếu cần)
                self._sse_queues[client_id].put(None)
                del self._sse_queues[client_id]

    def broadcast_event(self, event_type, data):
        print(f"--- DEBUG [EventManager]: Broadcasting event: Type={event_type}") # Log 1
        event_payload = {"event": event_type, "data": data}
        with self._lock:
            current_clients = list(self._sse_queues.keys())
            print(f"--- DEBUG [EventManager]: Broadcasting to clients: {current_clients}") # Log 2

        if not current_clients:
            print("--- DEBUG [EventManager]: No active SSE clients to broadcast to.") # Log nếu không có client

        for client_id in current_clients:
            try:
                q = None
                with self._lock:
                    if client_id in self._sse_queues:
                        q = self._sse_queues[client_id]
                if q:
                    print(f"--- DEBUG [EventManager]: Attempting to put event to queue for client: {client_id}") # Log 3
                    q.put_nowait(event_payload) # Dùng put_nowait để không bị block nếu queue đầy
                    print(f"--- DEBUG [EventManager]: Put successful for {client_id}") # Log 4
                else:
                    print(f"--- DEBUG [EventManager]: Queue not found for client {client_id} during broadcast")
            except queue.Full:
                print(f"!!! WARNING [EventManager]: SSE queue full for client {client_id}. Event lost.") # Cảnh báo quan trọng
            except Exception as e:
                print(f"!!! ERROR [EventManager]: Error putting event to queue for {client_id}: {e}")


    def broadcast_new_message(self, message_dict):
        self.broadcast_event("new_message", message_dict)

    def broadcast_agent_status(self, agent_id, status):
        status_data = {"agent_id": agent_id, "status": status}
        self.broadcast_event("agent_status", status_data)