# core/interaction_coordinator.py
import queue
import threading
import json
import uuid
import time
import random
from typing import Dict, Any, Optional
from core.conversation_history import ConversationHistory
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.response_orchestrator import ResponseOrchestrator

class InteractionCoordinator:
    def __init__(self, conversation_history: ConversationHistory):
        self.conv_history = conversation_history
        self.response_orchestrator: Optional['ResponseOrchestrator'] = None
        # <<< SSE queues are now nested: {session_id: {client_id: Queue}} >>>
        self._sse_queues: Dict[str, Dict[str, queue.Queue]] = {}
        self._lock = threading.Lock() # Lock protects the _sse_queues structure
        print("--- INT_COORD: Initialized (Session Aware).")

    def set_orchestrator(self, orchestrator: 'ResponseOrchestrator'):
         print("--- INT_COORD: Setting Response Orchestrator.")
         self.response_orchestrator = orchestrator

    # --- SSE Client Management (Session Aware) ---
    def add_sse_client(self, session_id: str, client_id: str) -> Optional[queue.Queue]:
        """Adds an SSE client queue for a specific session."""
        q = queue.Queue()
        with self._lock:
            # <<< Ensure session entry exists >>>
            if session_id not in self._sse_queues:
                self._sse_queues[session_id] = {}
            # <<< Add client to the session >>>
            self._sse_queues[session_id][client_id] = q
            print(f"--- INT_COORD [{session_id}]: SSE client added: {client_id}")
        return q

    def remove_sse_client(self, session_id: str, client_id: str):
         """Removes an SSE client queue for a specific session."""
         with self._lock:
             # <<< Check session and client existence >>>
             if session_id in self._sse_queues and client_id in self._sse_queues[session_id]:
                 q = self._sse_queues[session_id].pop(client_id, None)
                 if q:
                     try:
                          q.put_nowait(None) # Signal stop
                     except queue.Full: pass
                     except Exception as e: print(f"--- INT_COORD WARN [{session_id}]: Error putting None to queue for {client_id}: {e}")
                 print(f"--- INT_COORD [{session_id}]: SSE client removed: {client_id}")
                 # <<< Clean up session entry if no clients left >>>
                 if not self._sse_queues[session_id]:
                     del self._sse_queues[session_id]
                     print(f"--- INT_COORD [{session_id}]: No clients left, removed session entry.")

    def post_event_to_clients(self, session_id: str, event_type: str, source: str, content: Dict, is_internal: bool = False):
        """Posts an event to all connected SSE clients for a specific session."""
        # <<< Filter broadcast based on type >>>
        if event_type not in ["new_message", "agent_status", "system_message", "error"]:
             return

        print(f"--- INT_COORD [{session_id}]: Broadcasting SSE event: Type={event_type}, Source={source}")
        sse_data = {
            "event_id": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
            "event_type": event_type,
            "source": source,
            "content": content,
            "session_id": session_id # Include session_id in payload
        }
        sse_payload = {"event": event_type, "data": sse_data}

        client_queues_to_broadcast = []
        with self._lock:
            # <<< Get queues only for the target session >>>
            session_queues = self._sse_queues.get(session_id, {})
            client_queues_to_broadcast = list(session_queues.values())

        if not client_queues_to_broadcast:
            return

        for q in client_queues_to_broadcast:
            try:
                q.put_nowait(sse_payload)
            except queue.Full:
                print(f"!!! WARNING [InteractionCoordinator - {session_id}]: SSE queue full for a client. Event lost.")
            except Exception as e:
                print(f"!!! ERROR [InteractionCoordinator - {session_id}]: Error putting event to a client queue: {e}")

    # --- Trigger Handling (Session Aware) ---
    # <<< Add session_id parameter >>>
    def handle_external_trigger(self, session_id: str, event_type: str, source: str, content: Dict):
        """Handles triggers from outside (e.g., user message) for a specific session."""
        print(f"--- INT_COORD [{session_id}]: Received EXTERNAL trigger: Type={event_type}, Source={source}")
        # <<< Use session_id when adding event >>>
        logged_event = self.conv_history.add_event(session_id, event_type, source, content)
        if not logged_event: return

        # <<< Use session_id when posting to clients >>>
        self.post_event_to_clients(session_id, event_type, source, content)

        if self.response_orchestrator:
             # <<< Pass session_id to process_event >>>
             self.response_orchestrator.process_event(session_id=session_id, triggering_event=logged_event)
        else:
             print(f"--- INT_COORD [{session_id}]: Warning - Response Orchestrator not set.")

    # <<< Add session_id parameter >>>
    def handle_internal_trigger(self, session_id: str, event_type: str, source: str, content: Dict):
        """Handles triggers from within the system (e.g., agent speaking) for a specific session."""
        print(f"--- INT_COORD [{session_id}]: Received INTERNAL trigger: Type={event_type}, Source={source}")

        logged_event = None # Keep track if event was logged
        if event_type in ["new_message", "system_message", "phase_transition"]:
             # <<< Use session_id when adding event >>>
             logged_event = self.conv_history.add_event(session_id, event_type, source, content)
             if not logged_event: return

             # <<< Use session_id when posting to clients >>>
             self.post_event_to_clients(session_id, event_type, source, content)

             # Decide if internal event triggers further response
             if event_type == 'new_message' and self.response_orchestrator and logged_event:
                time.sleep(2) # wait prevent thinking too fast - be a good listener :)
                self.response_orchestrator.process_event(session_id=session_id, triggering_event=logged_event)
                print(f"--- INT_COORD [{session_id}]: Triggering orchestrator in response to internal message from {source}")
        else:
            # Handle non-logged internal events like agent_status
            if event_type == "agent_status":
                 # <<< Use session_id when posting to clients >>>
                self.post_event_to_clients(session_id, event_type, source, content, is_internal=True)
            else:
                print(f"--- INT_COORD [{session_id}]: Handling internal event type {event_type} (no DB log/broadcast).")

    def cleanup(self):
        # Logic remains the same, iterates through the nested structure
        print("--- INT_COORD: Cleanup initiated.")
        with self._lock:
            all_session_ids = list(self._sse_queues.keys())
            for session_id in all_session_ids:
                 client_ids = list(self._sse_queues.get(session_id, {}).keys())
                 for client_id in client_ids:
                      self.remove_sse_client(session_id, client_id) # Method handles nested removal
            self._sse_queues.clear()
        print("--- INT_COORD: Cleanup complete.")