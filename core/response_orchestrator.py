# core/response_orchestrator.py
import time
import threading
import traceback
from typing import Dict, Any, TYPE_CHECKING
from core.conversation_history import ConversationHistory
from core.conversation_phase_manager import ConversationPhaseManager
from core.agent_manager import AgentManager
from core.speaker_selector import SpeakerSelector
from core.behavior_executor import BehaviorExecutor

if TYPE_CHECKING:
    from core.interaction_coordinator import InteractionCoordinator # Avoid circular import

class ResponseOrchestrator:
    def __init__(self,
                 conversation_history: ConversationHistory,
                 phase_manager: ConversationPhaseManager,
                 agent_manager: AgentManager,
                 speaker_selector: SpeakerSelector,
                 behavior_executor: BehaviorExecutor,
                 interaction_coordinator: 'InteractionCoordinator',
                 problem_description: str): # Added problem
        self.conv_history = conversation_history
        self.phase_manager = phase_manager
        self.agent_manager = agent_manager
        self.speaker_selector = speaker_selector
        self.behavior_executor = behavior_executor
        self.interaction_coordinator = interaction_coordinator
        self.problem = problem_description # Store problem
        self._lock = threading.Lock()

    def _process_in_thread(self, triggering_event: Dict):
        acquired = self._lock.acquire(blocking=False)
        if not acquired:
             print(f"--- RESP_ORCH: Already processing another event. Skipping event {triggering_event['event_id']}.")
             return
        try:
            print(f"--- RESP_ORCH: Starting processing for event: {triggering_event['event_id']} ({triggering_event['event_type']})")
            start_time = time.time()

            # --- Core Logic ---
            # 1. Get Current Phase Context (triggers update)
            current_phase_context = self.phase_manager.get_current_phase(self.conv_history)
            current_history = self.conv_history.get_history() # Get latest history

            # 2. Trigger Parallel Thinking
            thinking_results = self.agent_manager.request_thinking(
                triggering_event, self.conv_history, self.phase_manager # PhaseManager updates internally
            )

            # 3. Evaluate Thoughts & Select Speaker
            selection = self.speaker_selector.select_speaker(
                thinking_results,
                current_phase_context, # Pass latest phase context
                current_history # Pass latest history
            )

            # 4. Trigger Execution if a speaker is selected
            if selection and selection.get("selected_agent_id"):
                self.behavior_executor.execute(
                    agent_id=selection["selected_agent_id"],
                    agent_name=selection["selected_agent_name"],
                    action=selection["selected_action"],
                    selected_thought_details=selection["selected_thought_details"], # Pass full thought details
                    phase_context=current_phase_context, # Pass context needed for CLASSMATE_SPEAK
                    history=current_history # Pass history needed for CLASSMATE_SPEAK
                )
            else:
                print("--- RESP_ORCH: No agent selected to speak for this event.")

            end_time = time.time()
            print(f"--- RESP_ORCH: Finished processing event {triggering_event['event_id']}. Duration: {end_time - start_time:.2f}s")

        except Exception as e:
            print(f"!!! ERROR [ResponseOrchestrator]: Failed during processing event {triggering_event.get('event_id', 'N/A')}: {e}")
            traceback.print_exc()
        finally:
             self._lock.release()

    # process_event method remains the same
    def process_event(self, triggering_event: Dict):
        thread = threading.Thread(target=self._process_in_thread, args=(triggering_event,), daemon=True)
        thread.start()