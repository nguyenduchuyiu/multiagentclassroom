# core/response_orchestrator.py
import time
import threading
import traceback
from typing import Dict, Any, TYPE_CHECKING, List
from flask import Flask # Import Flask if not already


from core.conversation_history import ConversationHistory
from core.conversation_phase_manager import ConversationPhaseManager
from core.agent_manager import AgentManager
from core.speaker_selector import SpeakerSelector
from core.behavior_executor import BehaviorExecutor

if TYPE_CHECKING:
    from core.interaction_coordinator import InteractionCoordinator

class ResponseOrchestrator:
    def __init__(self,
                 conversation_history: ConversationHistory,
                 phase_manager: ConversationPhaseManager,
                 agent_manager: AgentManager,
                 speaker_selector: SpeakerSelector,
                 behavior_executor: BehaviorExecutor,
                 interaction_coordinator: 'InteractionCoordinator',
                 problem_description: str,
                 app_instance):
        self.conv_history = conversation_history
        self.phase_manager = phase_manager
        self.agent_manager = agent_manager
        self.speaker_selector = speaker_selector
        self.behavior_executor = behavior_executor
        self.interaction_coordinator = interaction_coordinator
        self.problem = problem_description
        self.app = app_instance 
        self._lock = threading.Lock()

    def _process_in_thread(self, session_id: str, triggering_event: Dict):
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
             print(f"--- RESP_ORCH [{session_id}]: Orchestrator busy. Skipping event {triggering_event['event_id']}.")
             return

        # <<< Wrap context-dependent operations >>>
        with self.app.app_context():
            try:
                print(f"--- RESP_ORCH [{session_id}]: Starting processing for event: {triggering_event['event_id']} ({triggering_event['event_type']})")
                start_time = time.time()

                # --- Core Logic (Now within app context) ---
                current_phase_context = self.phase_manager.get_current_phase(session_id, self.conv_history)
                current_history = self.conv_history.get_history(session_id=session_id)

                thinking_results = self.agent_manager.request_thinking(
                    session_id=session_id,
                    triggering_event=triggering_event,
                    conversation_history=self.conv_history,
                    phase_manager=self.phase_manager
                )

                selection = self.speaker_selector.select_speaker(
                    session_id=session_id,
                    thinking_results=thinking_results,
                    phase_context=current_phase_context,
                    conversation_history=current_history
                )

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
                    print(f"--- RESP_ORCH [{session_id}]: No agent selected to speak for this event.")

                end_time = time.time()
                print(f"--- RESP_ORCH [{session_id}]: Finished processing event {triggering_event['event_id']}. Duration: {end_time - start_time:.2f}s")

            except Exception as e:
                # Log error within the context if possible
                print(f"!!! ERROR [ResponseOrchestrator - {session_id}]: Failed during processing event {triggering_event.get('event_id', 'N/A')}: {e}")
                traceback.print_exc()
            finally:
                 self._lock.release() # Release lock regardless of context success/failure

    def process_event(self, session_id: str, triggering_event: Dict):
        # The thread creation remains the same
        thread = threading.Thread(target=self._process_in_thread, args=(session_id, triggering_event,), daemon=True)
        thread.start()