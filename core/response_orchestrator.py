# core/response_orchestrator.py
import time
import threading
import traceback
from typing import Dict, Any, TYPE_CHECKING, List
from flask import Flask 


from core.conversation_history import ConversationHistory
from core.stage_management.conversation_phase_orchestrator import ConversationPhaseOrchestrator
from core.agent_manager import AgentManager
from core.speaker_selector import SpeakerSelector
from core.behavior_executor import BehaviorExecutor

if TYPE_CHECKING:
    from core.interaction_coordinator import InteractionCoordinator
#TODO: trigger phase manager first to provide context to agents.

class ResponseOrchestrator:
    def __init__(self,
                 conversation_history: ConversationHistory,
                 phase_manager: ConversationPhaseOrchestrator,
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
                # print(f"{log_prefix}: Starting processing for event: {triggering_event['event_id']} ({triggering_event['event_type']})")
                start_time = time.time()

                # Get Phase Context (needs context for DB access)
                current_phase_context = self.phase_manager.get_phase_context(session_id, self.conv_history)
                # print(f"--- RESP_ORCH [{session_id}]: Current phase context: {current_phase_context}")

                # <<< NEW: Send stage update to clients >>>
                if current_phase_context and 'id' in current_phase_context:
                    # --- NEW: Weighted progress calculation ---
                    all_phases_dict = self.phase_manager.get_all_phases()
                    sorted_phase_ids = sorted(all_phases_dict.keys()) # Assuming keys like "1", "2", "3", "4" sort naturally
                    num_main_stages = len(sorted_phase_ids)
                    
                    # progress_percent_for_bar sẽ giữ kết quả cuối cùng
                    progress_percent_for_bar = 0.0 

                    if num_main_stages > 0:
                        progress_per_main_stage_completion = 100.0 / num_main_stages
                        # Sử dụng một biến cục bộ cho việc tính toán trong vòng lặp
                        current_calculation_accumulated_progress = 0.0 
                        current_stage_id_str = str(current_phase_context.get("id"))
                        completed_tasks_map_from_context = current_phase_context.get('completed_tasks_map', {})
                        
                        log_prefix_calc = f"--- RESP_ORCH_WEIGHTED_CALC [{session_id}]"
                        print(f"{log_prefix_calc}: Starting weighted progress. Num main stages: {num_main_stages}, Progress per stage: {progress_per_main_stage_completion:.2f}%")
                        # Log thêm để kiểm tra completed_tasks_map_from_context nếu cần
                        print(f"{log_prefix_calc}: Initial completed_tasks_map_from_context: {completed_tasks_map_from_context}")

                        for phase_id_str in sorted_phase_ids:
                            phase_data = all_phases_dict[phase_id_str]
                            defined_tasks_for_phase = phase_data.get('tasks', [])
                            num_tasks_in_this_phase = len(defined_tasks_for_phase)
                            
                            completed_task_ids_for_this_phase = completed_tasks_map_from_context.get(phase_id_str, [])
                            num_completed_tasks_in_this_phase = len(completed_task_ids_for_this_phase)
                            
                            print(f"{log_prefix_calc}: Processing phase '{phase_id_str}': Defined tasks: {num_tasks_in_this_phase}, Completed: {num_completed_tasks_in_this_phase}")

                            if phase_id_str < current_stage_id_str:  # Previous stage
                                if num_tasks_in_this_phase > 0 and num_completed_tasks_in_this_phase >= num_tasks_in_this_phase:
                                    current_calculation_accumulated_progress += progress_per_main_stage_completion
                                    print(f"{log_prefix_calc}:   -> Previous & fully completed. Adding {progress_per_main_stage_completion:.2f}%. New total: {current_calculation_accumulated_progress:.2f}%")
                                elif num_tasks_in_this_phase == 0: # Previous stage with no tasks is considered complete
                                    current_calculation_accumulated_progress += progress_per_main_stage_completion
                                    print(f"{log_prefix_calc}:   -> Previous & no tasks. Adding {progress_per_main_stage_completion:.2f}%. New total: {current_calculation_accumulated_progress:.2f}%")
                                else:
                                    print(f"{log_prefix_calc}:   -> Previous but not fully completed. No progress added for this stage's segment.")
                            
                            elif phase_id_str == current_stage_id_str:
                                progress_for_this_stage_segment = 0.0
                                completion_ratio_current_stage = 0.0
                                if num_tasks_in_this_phase > 0:
                                    completion_ratio_current_stage = num_completed_tasks_in_this_phase / num_tasks_in_this_phase
                                    progress_for_this_stage_segment = completion_ratio_current_stage * progress_per_main_stage_completion
                                elif num_tasks_in_this_phase == 0: # Stage hiện tại không có task, coi như hoàn thành phần của nó
                                    completion_ratio_current_stage = 1.0
                                    progress_for_this_stage_segment = progress_per_main_stage_completion
                                
                                progress_before_current_segment = current_calculation_accumulated_progress # Giá trị trước khi cộng stage hiện tại
                                current_calculation_accumulated_progress += progress_for_this_stage_segment
                                
                                print(f"{log_prefix_calc}:   -> Current stage '{phase_id_str}'. Num tasks in this phase: {num_tasks_in_this_phase}, Num completed: {num_completed_tasks_in_this_phase}. Progress for this stage segment: {completion_ratio_current_stage:.2f} * {progress_per_main_stage_completion:.2f} = {progress_for_this_stage_segment:.2f}%")
                                print(f"{log_prefix_calc}:   Accumulated progress after current stage '{phase_id_str}': {progress_before_current_segment:.2f} + {progress_for_this_stage_segment:.2f} = {current_calculation_accumulated_progress:.2f}%")
                                print(f"{log_prefix_calc}:   Breaking after current stage '{phase_id_str}'.")
                                break 
                            else: 
                                # Future stage, not yet contributing to accumulated progress for the bar
                                print(f"{log_prefix_calc}:   -> Future stage '{phase_id_str}'. Stopping calculation for bar.")
                                break 
                        
                        # GÁN GIÁ TRỊ QUAN TRỌNG:
                        # Sau khi vòng lặp kết thúc (hoặc break), gán kết quả tính toán được cho progress_percent_for_bar
                        progress_percent_for_bar = current_calculation_accumulated_progress
                    
                    # --- NEW: KIỂM TRA VÀ GHI ĐÈ NẾU STAGE HIỆN TẠI LÀ STAGE CUỐI VÀ ĐÃ HOÀN THÀNH ---
                    if sorted_phase_ids: # Đảm bảo danh sách phase không rỗng
                        last_stage_id_in_process = sorted_phase_ids[-1]
                        current_stage_id_from_context = str(current_phase_context.get("id"))

                        if current_stage_id_from_context == last_stage_id_in_process:
                            # Stage hiện tại đang active chính là stage cuối cùng của toàn bộ quy trình
                            # Kiểm tra xem stage cuối này đã hoàn thành chưa
                            tasks_in_current_last_stage = all_phases_dict[current_stage_id_from_context].get('tasks', [])
                            num_total_tasks_in_current_last_stage = len(tasks_in_current_last_stage)
                            
                            completed_tasks_for_current_last_stage_list = completed_tasks_map_from_context.get(current_stage_id_from_context, [])
                            num_completed_tasks_in_current_last_stage = len(completed_tasks_for_current_last_stage_list)
                            
                            is_current_last_stage_fully_complete = (num_completed_tasks_in_current_last_stage >= num_total_tasks_in_current_last_stage) or \
                                                                 (num_total_tasks_in_current_last_stage == 0)
                            
                            if is_current_last_stage_fully_complete:
                                progress_percent_for_bar = 100.0
                                print(f"{log_prefix_calc}: Active stage ('{current_stage_id_from_context}') is the LAST stage of the process and is fully complete. Overriding progress to 100%.")
                    # --- END NEW ---

                    print(f"{log_prefix_calc}: Final weighted progress_percent_for_bar (to be sent): {progress_percent_for_bar:.2f}%")
                    # <<< NEW: Get main stage display info >>>
                    main_stage_markers = []
                    for stage_id_key in sorted_phase_ids:
                        main_stage_markers.append({
                            "id": stage_id_key,
                            "name": all_phases_dict[stage_id_key].get("name", f"Giai đoạn {stage_id_key}") # Or just the ID
                        })
                    # <<< END NEW >>>

                    stage_update_content = {
                        "id": current_phase_context.get("id"),
                        "name": current_phase_context.get("name"),
                        "description": current_phase_context.get("description", ""),
                        "tasks": current_phase_context.get("tasks_for_display", []),
                        "progress_bar_percent": progress_percent_for_bar, # Sử dụng giá trị đã được gán đúng
                        "main_stage_markers": main_stage_markers
                    }
                    
                    print(f"--- RESP_ORCH [{session_id}]: Stage update content: {stage_update_content}")
                    
                    self.interaction_coordinator.post_event_to_clients(
                        session_id=session_id,
                        event_type="stage_update",
                        source="System",
                        content=stage_update_content,
                        is_internal=True
                    )
                # <<< END NEW >>>
                
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