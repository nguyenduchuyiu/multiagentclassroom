# core/response_orchestrator.py
import time
import threading
import traceback
from typing import Dict, Any, TYPE_CHECKING, List
from flask import Flask 


from core.conversation_history import ConversationHistory
from core.conversation_phase_manager import ConversationPhaseManager
from core.agent_manager import AgentManager
from core.speaker_selector import SpeakerSelector
from core.behavior_executor import BehaviorExecutor

if TYPE_CHECKING:
    from core.interaction_coordinator import InteractionCoordinator
#TODO: trigger phase manager first to provide context to agents.

class ResponseOrchestrator:
    def __init__(self,
                 conversation_history: ConversationHistory,
                 phase_manager: ConversationPhaseManager,
                 agent_manager: AgentManager,
                 speaker_selector: SpeakerSelector,
                 behavior_executor: BehaviorExecutor,
                 interaction_coordinator: 'InteractionCoordinator',
                 problem_description: str,
                 app_instance: Flask): # Added app_instance
        self.conv_history = conversation_history
        self.phase_manager = phase_manager
        self.agent_manager = agent_manager
        self.speaker_selector = speaker_selector
        self.behavior_executor = behavior_executor
        self.interaction_coordinator = interaction_coordinator
        self.problem = problem_description
        self.app = app_instance # Store app instance
        self._lock = threading.Lock()

    def _process_in_thread(self, session_id: str, triggering_event: Dict):
        """The actual processing logic running in a separate thread with app context."""
        
        if not self.interaction_coordinator.has_active_clients(session_id):
             print(f"--- RESP_ORCH [{session_id}]: No active clients. Skipping processing for event {triggering_event['event_id']}.")
             return
             
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
             print(f"--- RESP_ORCH [{session_id}]: Orchestrator busy. Skipping event {triggering_event['event_id']}.")
             return

        # Use the stored app instance to push context
        with self.app.app_context():
            try:
                log_prefix = f"--- RESP_ORCH [{session_id}]"
                print(f"{log_prefix}: Starting processing for event: {triggering_event['event_id']} ({triggering_event['event_type']})")
                start_time = time.time()

                # Get Phase Context (needs context for DB access)
                current_phase_context = self.phase_manager.get_phase_context(session_id, self.conv_history)
                # Get History (needs context for DB access)
                current_history = self.conv_history.get_history(session_id=session_id)
                
                # Trigger Parallel Thinking (AgentManager needs context pushed in its threads)
                thinking_results = self.agent_manager.request_thinking(
                    session_id=session_id,
                    triggering_event=triggering_event,
                    conversation_history=self.conv_history,
                    phase_manager=self.phase_manager,
                )

                # Evaluate Thoughts & Select Speaker (needs context for DB access)
                selection = self.speaker_selector.select_speaker(
                    session_id=session_id,
                    thinking_results=thinking_results,
                    phase_context=current_phase_context,
                    conversation_history=current_history # Pass the list
                )

                # Trigger Execution (BehaviorExecutor needs context pushed in its threads)
                if selection and selection.get("selected_agent_id"):
                    self.behavior_executor.execute(
                        session_id=session_id,
                        agent_id=selection["selected_agent_id"],
                        agent_name=selection["selected_agent_name"],
                        action=selection["selected_action"],
                        selected_thought_details=selection["selected_thought_details"],
                        phase_context=current_phase_context,
                        history=current_history
                    )
                else:
                    print(f"{log_prefix}: No agent selected to speak for this event.")

                end_time = time.time()
                print(f"{log_prefix}: Finished processing event {triggering_event['event_id']}. Duration: {end_time - start_time:.2f}s")

            except Exception as e:
                print(f"!!! ERROR [{log_prefix}]: Failed during processing event {triggering_event.get('event_id', 'N/A')}: {e}")
                traceback.print_exc()
            finally:
                 self._lock.release()

    def process_event(self, session_id: str, triggering_event: Dict):
        """Starts the response generation flow in a separate thread."""
        thread = threading.Thread(target=self._process_in_thread, args=(session_id, triggering_event,), daemon=True)
        thread.start()