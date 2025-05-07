# core/interaction_coordinator.py
import queue
import threading
import uuid
import time
from typing import Dict, Any, Optional
from core.conversation_history import ConversationHistory
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.response_orchestrator import ResponseOrchestrator

class InteractionCoordinator:
    def __init__(self, conversation_history: ConversationHistory):
        self.conv_history = conversation_history
        self.response_orchestrator: Optional['ResponseOrchestrator'] = None
        self._sse_queues: Dict[str, Dict[str, queue.Queue]] = {}
        self._lock = threading.Lock()
        print("--- INT_COORD: Initialized (Session Aware).")

    def set_orchestrator(self, orchestrator: 'ResponseOrchestrator'):
         print("--- INT_COORD: Setting Response Orchestrator.")
         self.response_orchestrator = orchestrator

    # --- SSE Client Management (Session Aware) ---
    def add_sse_client(self, session_id: str, client_id: str) -> Optional[queue.Queue]:
        q = queue.Queue()
        with self._lock:
            if session_id not in self._sse_queues:
                self._sse_queues[session_id] = {}
            self._sse_queues[session_id][client_id] = q
            print(f"--- INT_COORD [{session_id}]: SSE client added: {client_id}")
        return q

    def remove_sse_client(self, session_id: str, client_id: str):
         with self._lock:
             if session_id in self._sse_queues and client_id in self._sse_queues[session_id]:
                 q = self._sse_queues[session_id].pop(client_id, None)
                 if q:
                     try: q.put_nowait(None)
                     except queue.Full: pass
                     except Exception as e: print(f"--- INT_COORD WARN [{session_id}]: Error putting None to queue for {client_id}: {e}")
                 print(f"--- INT_COORD [{session_id}]: SSE client removed: {client_id}")
                 if not self._sse_queues[session_id]:
                     del self._sse_queues[session_id]
                     print(f"--- INT_COORD [{session_id}]: No clients left, removed session entry.")

    def post_event_to_clients(self, session_id: str, event_type: str, source: str, content: Dict, is_internal: bool = False, metadata: Optional[Dict] = None):
        if event_type not in ["new_message", "agent_status", "system_message", "error"]:
             return

        print(f"--- INT_COORD [{session_id}]: Broadcasting SSE event: Type={event_type}, Source={source}")
        sse_data = {
            "event_id": str(uuid.uuid4()),
            "timestamp": int(time.time() * 1000),
            "event_type": event_type,
            "source": source,
            "content": content,
            "session_id": session_id,
            "metadata": metadata or {} # Include metadata if provided
        }
        sse_payload = {"event": event_type, "data": sse_data}

        client_queues_to_broadcast = []
        with self._lock:
            session_queues = self._sse_queues.get(session_id, {})
            client_queues_to_broadcast = list(session_queues.values())

        if not client_queues_to_broadcast: return

        for q in client_queues_to_broadcast:
            try: q.put_nowait(sse_payload)
            except queue.Full: print(f"!!! WARNING [InteractionCoordinator - {session_id}]: SSE queue full for a client.")
            except Exception as e: print(f"!!! ERROR [InteractionCoordinator - {session_id}]: Error putting event to a client queue: {e}")
            
    def _delayed_orchestrator_trigger(self, session_id: str, triggering_event: Dict):
        """Helper function called by the Timer."""
        if self.response_orchestrator:
            print(f"--- INT_COORD [{session_id}]: Delayed trigger for orchestrator.")
            self.response_orchestrator.process_event(session_id=session_id, triggering_event=triggering_event)
        else:
            print(f"--- INT_COORD [{session_id}]: Warning - Orchestrator not set for delayed trigger.")
            
    # --- Trigger Handling (Session Aware) ---
    def handle_external_trigger(self, session_id: str, event_type: str, source: str, content: Dict):
        print(f"--- INT_COORD [{session_id}]: Received EXTERNAL trigger: Type={event_type}, Source={source}")
        # Log event first (needs app context via ConversationHistory methods)
        logged_event = self.conv_history.add_event(session_id, event_type, source, content)
        if not logged_event: return

        # Broadcast to clients
        self.post_event_to_clients(session_id, event_type, source, content, metadata=logged_event.get("metadata"))

        # Trigger orchestrator
        if self.response_orchestrator:
             delay = 2 # wait in case user enters more input 
             print(f"--- INT_COORD [{session_id}]: Scheduling orchestrator trigger after {delay:.2f}s delay (external).")
             timer = threading.Timer(delay, self._delayed_orchestrator_trigger, args=[session_id, logged_event])
             timer.start()
        else:
             print(f"--- INT_COORD [{session_id}]: Warning - Response Orchestrator not set.")

    def handle_internal_trigger(self, session_id: str, event_type: str, source: str, content: Dict):
        print(f"--- INT_COORD [{session_id}]: Received INTERNAL trigger: Type={event_type}, Source={source}")
        logged_event = None
        # Log significant internal events (needs app context via ConversationHistory methods)
        if event_type in ["new_message", "system_message", "phase_transition"]:
             logged_event = self.conv_history.add_event(session_id, event_type, source, content)
             if not logged_event: return

             # Broadcast logged internal events
             self.post_event_to_clients(session_id, event_type, source, content, metadata=logged_event.get("metadata"))

             # Trigger orchestrator for agent messages
             if event_type == 'new_message' and self.response_orchestrator and logged_event:
                time.sleep(2) # wait in case user enter more input
                print(f"--- INT_COORD [{session_id}]: Triggering orchestrator in response to internal message from {source}")
                self.response_orchestrator.process_event(session_id=session_id, triggering_event=logged_event)

        elif event_type == "agent_status":
            # Broadcast non-logged status updates
            self.post_event_to_clients(session_id, event_type, source, content, is_internal=True)
        else:
            print(f"--- INT_COORD [{session_id}]: Handling internal event type {event_type} (no DB log/broadcast/trigger).")

    def cleanup(self):
        print("--- INT_COORD: Cleanup initiated.")
        with self._lock:
            all_session_ids = list(self._sse_queues.keys())
            for session_id in all_session_ids:
                 client_ids = list(self._sse_queues.get(session_id, {}).keys())
                 for client_id in client_ids:
                      self.remove_sse_client(session_id, client_id)
            self._sse_queues.clear()
        print("--- INT_COORD: Cleanup complete.")
        
    def has_active_clients(self, session_id: str) -> bool:
        """Checks if there are any active SSE clients for the session."""
        with self._lock:
            return session_id in self._sse_queues and bool(self._sse_queues[session_id])