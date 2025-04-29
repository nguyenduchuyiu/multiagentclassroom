# core/interaction_coordinator.py
import queue
import threading
import json
import uuid
import time
import random
from typing import Dict, Any
from core.conversation_history import ConversationHistory
from core.response_orchestrator import ResponseOrchestrator
# BehaviorExecutor is mainly called by ResponseOrchestrator, but IC might need it for direct actions?

class InteractionCoordinator:
    def __init__(self, conversation_history: ConversationHistory):
        self.conv_history = conversation_history
        # These will be set after initialization by app.py to avoid circular dependencies during init
        self.response_orchestrator: ResponseOrchestrator = None
        # self.behavior_executor: BehaviorExecutor = None # Maybe not needed directly

        self._sse_queues: Dict[str, queue.Queue] = {}
        self._lock = threading.Lock() # Lock for SSE queues

        print("--- INT_COORD: Initialized.")

    def set_orchestrator(self, orchestrator: ResponseOrchestrator):
         print("--- INT_COORD: Setting Response Orchestrator.")
         self.response_orchestrator = orchestrator

    # --- SSE Client Management (Similar to old EventManager) ---
    def add_sse_client(self, client_id: str) -> queue.Queue:
        q = queue.Queue()
        with self._lock:
            self._sse_queues[client_id] = q
            print(f"--- INT_COORD: SSE client added: {client_id}")
        return q

    def remove_sse_client(self, client_id: str):
         with self._lock:
             if client_id in self._sse_queues:
                 try:
                      self._sse_queues[client_id].put_nowait(None) # Signal stop
                 except queue.Full: pass
                 except Exception as e: print(f"--- INT_COORD WARN: Error putting None to queue for {client_id}: {e}")
                 del self._sse_queues[client_id]
                 print(f"--- INT_COORD: SSE client removed: {client_id}")

    def post_event_to_clients(self, event_type: str, source: str, content: Dict, is_internal: bool = False):
        """Posts an event to all connected SSE clients."""
        # Decide if this event should be broadcast (e.g., don't broadcast internal thinking steps)
        if event_type not in ["new_message", "agent_status"]: # Only broadcast messages and status for now
             # print(f"--- INT_COORD: Skipping broadcast for internal/non-UI event type: {event_type}")
             return

        print(f"--- INT_COORD: Broadcasting SSE event: Type={event_type}, Source={source}")
        # Structure the data payload for SSE
        sse_data = {
            "event_id": str(uuid.uuid4()), # Unique ID for the SSE transmission itself
            "timestamp": int(time.time() * 1000),
            "event_type": event_type,
            "source": source,
            "content": content,
        }
        sse_payload = {"event": event_type, "data": sse_data} # Wrap for SSE format

        client_ids_to_broadcast = []
        with self._lock:
            client_ids_to_broadcast = list(self._sse_queues.keys())

        if not client_ids_to_broadcast:
            # print("--- INT_COORD: No active SSE clients.")
            return

        for client_id in client_ids_to_broadcast:
            q = None
            with self._lock:
                q = self._sse_queues.get(client_id)
            if q:
                try:
                    q.put_nowait(sse_payload)
                except queue.Full:
                    print(f"!!! WARNING [InteractionCoordinator]: SSE queue full for client {client_id}. Event lost.")
                except Exception as e:
                    print(f"!!! ERROR [InteractionCoordinator]: Error putting event to queue for {client_id}: {e}")


    # --- Trigger Handling ---
    def handle_external_trigger(self, event_type: str, source: str, content: Dict):
        """Handles triggers from outside the core loop (e.g., user message)."""
        print(f"--- INT_COORD: Received EXTERNAL trigger: Type={event_type}, Source={source}")
        # 1. Log the event immediately
        logged_event = self.conv_history.add_event(event_type, source, content)

        # 2. Broadcast to clients (if relevant type)
        self.post_event_to_clients(event_type, source, content)

        # 3. Trigger the Response Orchestrator to potentially generate an AI response
        if self.response_orchestrator:
             # Apply a small random delay before triggering response to feel more natural
             # delay = random.uniform(0.1, 0.5)
             # time.sleep(delay) # Consider if blocking here is okay, or use Timer
             self.response_orchestrator.process_event(logged_event)
        else:
             print("--- INT_COORD: Warning - Response Orchestrator not set. Cannot process event further.")


    def handle_internal_trigger(self, event_type: str, source: str, content: Dict):
        """Handles triggers from within the system (e.g., agent finished speaking)."""
        print(f"--- INT_COORD: Received INTERNAL trigger: Type={event_type}, Source={source}")
        # 1. Log the event
        # Decide if *all* internal events need logging, maybe based on type
        # For now, log messages generated internally
        if event_type == "new_message":
             logged_event = self.conv_history.add_event(event_type, source, content)
             # Apply random pause *before* broadcasting the AI message
             # delay = random.uniform(0.2, 1.0)
             # print(f"--- INT_COORD: Applying random pause before posting AI message: {delay:.2f}s")
             # time.sleep(delay) # Blocking delay, consider Timer if IC needs to be responsive

             # Broadcast the NEW message generated internally
             self.post_event_to_clients(event_type, source, content)

             # IMPORTANT: Decide if an internal message should *also* trigger the response orchestrator
             # Usually, an agent speaking shouldn't immediately trigger another round of thinking
             # unless it's a specific multi-turn action. For now, we DON'T trigger RO here.
             # if self.response_orchestrator:
             #     self.response_orchestrator.process_event(logged_event)
        else:
             # Handle other internal events (logging, status updates, etc.)
             # Maybe broadcast some internal events like 'evaluation_complete' if needed for UI?
             print(f"--- INT_COORD: Handling internal event type {event_type} (currently no action/broadcast).")


    def cleanup(self):
        # Clean up resources if needed (e.g., stop timers)
        print("--- INT_COORD: Cleanup initiated.")
        # Signal all SSE clients to stop
        client_ids = list(self._sse_queues.keys())
        for client_id in client_ids:
             self.remove_sse_client(client_id)
        print("--- INT_COORD: Cleanup complete.")