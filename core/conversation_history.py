# core/conversation_history.py
import time
import uuid
import threading
from utils.helpers import get_timestamp

class ConversationHistory:
    def __init__(self):
        self._log = [] # List of event dictionaries
        self._lock = threading.Lock()

    def add_event(self, event_type: str, source: str, content: dict, metadata: dict = None):
        """Adds a structured event to the history."""
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": get_timestamp(),
            "event_type": event_type, # e.g., 'new_message', 'agent_thinking', 'silence_pause'
            "source": source,       # e.g., 'Human', agent_id, 'System'
            "content": content,     # e.g., {'text': 'Hello'}, {'thoughts': '...'}
            "metadata": metadata or {} # e.g., {'phase_id': 'greeting'}
        }
        with self._lock:
            self._log.append(event)
            # Simple console log for now
            print(f"HIST LOG: [{event['event_type']}] Source={source}, Content={content}")
        return event # Return the added event

    def get_history(self, count=None):
        """Returns a copy of the event log."""
        with self._lock:
            if count:
                return list(self._log[-count:])
            return list(self._log)

    def get_last_event(self):
        with self._lock:
            return self._log[-1] if self._log else None

    # Add other methods as needed (e.g., filter by type/source)