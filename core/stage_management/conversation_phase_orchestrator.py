# core/stage_management/conversation_phase_orchestrator.py
import json
import traceback
from typing import Dict, Any, List

from flask import Flask
from core.conversation_history import ConversationHistory # Assuming this path is correct
from services.llm_service import LLMService # Assuming this path is correct
from core.prompt_templates import STAGE_MANAGER_PROMPT # Assuming this path is correct

# New imports for refactored components
from core.stage_management.phase_config_loader import PhaseConfigLoader
from core.stage_management.session_state_manager import SessionStateManager
from core.stage_management.task_formatter import TaskFormatter
from utils.helpers import clean_response, parse_json_response # Add this if not present


class ConversationPhaseOrchestrator:
    def __init__(self, phase_config_path: str, problem_description: str, llm_service: LLMService, app_instance: Flask):
        self.app = app_instance 
        self.problem_description = problem_description
        self.llm_service = llm_service
        
        self.phase_config_loader = PhaseConfigLoader(phase_config_path)
        self.session_state_manager = SessionStateManager(app_instance)
        self.task_formatter = TaskFormatter(self.phase_config_loader)
        
        print(f"--- ConversationPhaseOrchestrator: Initialized.")

    def _format_history_for_prompt(self, history: List[Dict], count=100) -> str:
        recent_history = history[-count:]
        lines = []
        for i, event in enumerate(recent_history):
            text = event.get('content', {}).get('text', '(Non-message event)')
            source_display = event.get('content', {}).get('sender_name', event.get('source', 'Unknown'))
            lines.append(f"CON#{i+1} {source_display}: {text}")
        return "\n".join(lines) if lines else "Chưa có hội thoại."

    def _mark_task_complete_logic(self, session_id: str, task_id_to_complete: str):
        # This method assumes it's called within an app_context
        current_phase_id_from_db, completed_tasks_map = self.session_state_manager.get_session_state(session_id)
        print(f"Debug (Orchestrator._mark_task_complete_logic): last known phase id from DB is '{current_phase_id_from_db}' for session '{session_id}' when attempting to mark task '{task_id_to_complete}'.")

        phase_to_update_tasks_for = current_phase_id_from_db
        phase_data = self.phase_config_loader.get_phase_data(phase_to_update_tasks_for)

        if not phase_data:
            print(f"!!! WARN [Orchestrator - {session_id}]: Phase '{phase_to_update_tasks_for}' (for task '{task_id_to_complete}') not defined. Skipping task mark.")
            return

        if not isinstance(completed_tasks_map, dict):
            print(f"!!! WARN [Orchestrator - {session_id}]: completed_tasks_map is not a dict. Initializing.")
            completed_tasks_map = {}

        if phase_to_update_tasks_for not in completed_tasks_map:
            completed_tasks_map[phase_to_update_tasks_for] = []
        elif not isinstance(completed_tasks_map[phase_to_update_tasks_for], list):
            print(f"!!! WARN [Orchestrator - {session_id}]: Tasks for phase '{phase_to_update_tasks_for}' was not a list. Resetting.")
            completed_tasks_map[phase_to_update_tasks_for] = []

        defined_tasks_for_phase_map = self.phase_config_loader.get_task_map_for_phase(phase_to_update_tasks_for)
        str_task_id_to_complete = str(task_id_to_complete)

        if str_task_id_to_complete not in defined_tasks_for_phase_map:
            print(f"!!! WARN [Orchestrator - {session_id}]: Task ID '{str_task_id_to_complete}' not defined for phase '{phase_to_update_tasks_for}'. Defined: {list(defined_tasks_for_phase_map.keys())}. Skipping.")
            return

        if str_task_id_to_complete not in [str(t) for t in completed_tasks_map[phase_to_update_tasks_for]]:
            completed_tasks_map[phase_to_update_tasks_for].append(str_task_id_to_complete)
            print(f"--- Orchestrator [{session_id}]: Marking task '{str_task_id_to_complete}' as complete for phase '{phase_to_update_tasks_for}'.")
            self.session_state_manager.update_session_state(session_id, current_phase_id_from_db, completed_tasks_map)
        else:
            print(f"--- Orchestrator [{session_id}]: Task '{str_task_id_to_complete}' already complete for phase '{phase_to_update_tasks_for}'.")

    def mark_task_complete(self, session_id: str, task_id_to_complete: str):
        """Public method to mark a task as complete directly."""
        with self.app.app_context():
            self._mark_task_complete_logic(session_id, task_id_to_complete)

    def get_all_phases(self) -> Dict[str, Any]:
        """Get all phases from the phase config loader."""
        return self.phase_config_loader.get_all_phases()

    def get_phase_context(self, session_id: str, conversation_history: ConversationHistory) -> Dict[str, Any]:
        print(f"--- TOP_LEVEL_DEBUG [Orchestrator - {session_id}]: Method get_phase_context CALLED.")
        try:
            print(f"--- TOP_LEVEL_DEBUG [Orchestrator - {session_id}]: Inside try block. self.app type: {type(self.app)}, self.app is None: {self.app is None}")
            if self.app is None:
                print(f"!!! CRITICAL_ERROR [Orchestrator - {session_id}]: self.app is None in get_phase_context! Cannot proceed with app_context.")
                # Return an error structure indicating a server-side configuration issue
                return {
                    "id": "APP_INIT_ERROR", 
                    "name": "Application Context Error", 
                    "description": "Internal server error: Application context not available.", 
                    "tasks_for_display": [], 
                    "goals": [], 
                    "task_status_prompt": "Lỗi ngữ cảnh ứng dụng.", 
                    "completed_tasks_map": {}
                }

            with self.app.app_context():
                print(f"--- DEBUG [Orchestrator - {session_id}]: Entered app_context in get_phase_context.")
                last_known_phase_id, completed_tasks_map_before_llm = self.session_state_manager.get_session_state(session_id)
                print(f"--- DEBUG [Orchestrator - {session_id}]: After get_session_state. Phase: '{last_known_phase_id}'.")
                print(f"Debug (Orchestrator.get_phase_context start): last known phase id from DB is '{last_known_phase_id}' for session '{session_id}'.")

                history_log = conversation_history.get_history(session_id=session_id)
                current_phase_def_for_llm_prompt = self.phase_config_loader.get_phase_data(last_known_phase_id)
                print(f"--- DEBUG [Orchestrator - {session_id}]: About to check phase config for phase '{last_known_phase_id}'.")

                if not current_phase_def_for_llm_prompt:
                    print(f"!!! ERROR [Orchestrator - {session_id}]: Config for last known phase '{last_known_phase_id}' not found. Defaulting to '1'.")
                    last_known_phase_id = "1"
                    current_phase_def_for_llm_prompt = self.phase_config_loader.get_phase_data("1")
                    if not current_phase_def_for_llm_prompt:
                        return {"id": "?", "name": "Config Error", "description": "Phase configuration missing.", "tasks_for_display": [], "goals": [], "task_status_prompt": "Lỗi cấu hình giai đoạn.", "completed_tasks_map": {}}

                current_stage_desc_prompt = f"Giai đoạn hiện tại (ID: {last_known_phase_id}): {current_phase_def_for_llm_prompt.get('name', '')}\n"
                current_stage_desc_prompt += f"Mô tả giai đoạn: {current_phase_def_for_llm_prompt.get('description', '')}\n"
                current_stage_desc_prompt += "Danh sách nhiệm vụ của giai đoạn này (ID, trạng thái [X] Hoàn thành / [ ] Chưa, và mô tả):\n"
                
                tasks_for_llm_prompt = current_phase_def_for_llm_prompt.get('tasks', [])
                completed_ids_for_this_phase_in_prompt = [str(tid) for tid in completed_tasks_map_before_llm.get(last_known_phase_id, [])]

                next_task_found_for_prompt = False # Initialize here
                print(f"--- DEBUG [Orchestrator - {session_id}]: About to build task list for prompt. tasks_for_llm_prompt: {tasks_for_llm_prompt}")
                if tasks_for_llm_prompt:
                    for t_dict in tasks_for_llm_prompt:
                        task_id = t_dict.get('id')
                        task_desc = t_dict.get('description')
                        if task_id and task_desc:
                            is_done = str(task_id) in completed_ids_for_this_phase_in_prompt
                            marker = "[X]" if is_done else "[ ]"
                            next_marker_text = ""
                            if not is_done and not next_task_found_for_prompt:
                                next_marker_text = " <-- Nhiệm vụ tiếp theo cần tập trung"
                                next_task_found_for_prompt = True
                            current_stage_desc_prompt += f"- {marker} ({task_id}) {task_desc}{next_marker_text}\n"
                        else:
                            current_stage_desc_prompt += f"- (Nhiệm vụ không hợp lệ: {t_dict})\n"
                else:
                    current_stage_desc_prompt += "- (Không có nhiệm vụ cụ thể nào được liệt kê cho giai đoạn này)\n"
                
                current_stage_desc_prompt += "Mục tiêu của giai đoạn:\n"
                
                goals_list = current_phase_def_for_llm_prompt.get('goals', [])
                if goals_list:
                    current_stage_desc_prompt += "\n".join([f"- {g}" for g in goals_list])
                else:
                    current_stage_desc_prompt += "(Không có mục tiêu cụ thể cho giai đoạn này)"

                print("Current stage description prompt: ", current_stage_desc_prompt)

                prompt = STAGE_MANAGER_PROMPT.format(
                    problem=self.problem_description,
                    current_stage_description=current_stage_desc_prompt.strip(),
                    history=self._format_history_for_prompt(history_log)
                )

                print(f"--- Orchestrator [{session_id}]: Requesting phase signal & task completion from LLM (based on stage {last_known_phase_id})...")
                
                try:
                    raw_response = self.llm_service.generate(prompt)
                    raw_response_for_log = raw_response
                    print(f"--- Orchestrator [{session_id}]: Raw LLM Signal Response (get_phase_context): {raw_response}")
                    
                    parsed_output = None # Initialize parsed_output
                    # Use helper functions for cleaning and parsing
                    cleaned_llm_response = clean_response(raw_response)
                    parsed_output = parse_json_response(cleaned_llm_response)

                    if not parsed_output:
                        print(f"!!! WARN [Orchestrator - {session_id}]: Failed to parse LLM JSON response (get_phase_context). Raw: {raw_response_for_log}")
                        # parsed_output remains None, subsequent .get calls will safely return None

                    # The rest of the logic from line 158 onwards uses parsed_output:
                    # if parsed_output: # This check might already be implicitly handled by .get
                    signal_data = parsed_output.get("signal") if parsed_output else None
                    raw_completed_task_ids_from_llm = parsed_output.get("completed_task_ids", []) if parsed_output else []
                    
                    if isinstance(raw_completed_task_ids_from_llm, list):
                        completed_task_ids_from_llm = [str(tid).strip() for tid in raw_completed_task_ids_from_llm if isinstance(tid, (str, int, float)) and str(tid).strip()]
                    else:
                        print(f"!!! WARN [Orchestrator - {session_id}]: 'completed_task_ids' from LLM is not a list: {raw_completed_task_ids_from_llm}. Ignoring.")
                    
                    if isinstance(signal_data, list) and len(signal_data) == 2:
                        _, signal_text_from_llm = map(str, signal_data)
                        llm_determined_signal_text = signal_text_from_llm.strip()
                    elif signal_data:
                        print(f"!!! WARN [Orchestrator - {session_id}]: Invalid 'signal' format from LLM: {signal_data}. Defaulting signal.")
                    
                    print(f"--- Orchestrator [{session_id}]: LLM Signal: '{llm_determined_signal_text}'. Tasks suggested by LLM: {completed_task_ids_from_llm}.")
                
                except Exception as e: # Catch any other unexpected errors during LLM call or initial processing
                    print(f"!!! ERROR [Orchestrator - {session_id}]: Error during LLM interaction in get_phase_context: {e}")
                    traceback.print_exc()
                    # Ensure defaults are set if LLM call fails catastrophically before parsing
                    llm_determined_signal_text = "Tiếp tục" # Fallback
                    completed_task_ids_from_llm = []       # Fallback
                    # parsed_output will be None or from a failed attempt

                if completed_task_ids_from_llm:
                    defined_task_ids_for_prompted_phase = self.phase_config_loader.get_task_map_for_phase(last_known_phase_id).keys()
                    for task_id_from_llm in completed_task_ids_from_llm:
                        str_task_id_from_llm = str(task_id_from_llm)
                        if str_task_id_from_llm in defined_task_ids_for_prompted_phase:
                            self._mark_task_complete_logic(session_id, str_task_id_from_llm) # Already in app_context
                        else:
                            print(f"!!! WARN [Orchestrator - {session_id}]: LLM suggested task '{str_task_id_from_llm}' (phase '{last_known_phase_id}') not defined. Discarding.")
                
                current_phase_id_for_logic, completed_tasks_map_after_llm_updates = self.session_state_manager.get_session_state(session_id)
                
                final_phase_id_for_context = current_phase_id_for_logic
                final_completed_tasks_map_for_context = json.loads(json.dumps(completed_tasks_map_after_llm_updates)) 

                if llm_determined_signal_text == "Chuyển stage mới":
                    tasks_in_current_phase_logic_def = self.phase_config_loader.get_defined_tasks_for_phase(current_phase_id_for_logic)
                    defined_task_ids_current_phase_logic = {str(t['id']) for t in tasks_in_current_phase_logic_def if isinstance(t, dict) and 'id' in t}
                    
                    completed_ids_current_phase_logic_list = final_completed_tasks_map_for_context.get(current_phase_id_for_logic, [])
                    completed_ids_current_phase_logic_set = {str(tid) for tid in completed_ids_current_phase_logic_list}

                    all_tasks_of_current_phase_completed = defined_task_ids_current_phase_logic.issubset(completed_ids_current_phase_logic_set)

                    if not all_tasks_of_current_phase_completed and defined_task_ids_current_phase_logic:
                        print(f"--- Orchestrator [{session_id}]: LLM signaled 'Chuyển stage mới', but not all tasks for phase '{current_phase_id_for_logic}' are complete. Staying.")
                        self.session_state_manager.update_session_state(session_id, current_phase_id_for_logic, final_completed_tasks_map_for_context)
                    else:
                        try:
                            next_phase_int = int(current_phase_id_for_logic) + 1
                            next_phase_id_str = str(next_phase_int)
                            if self.phase_config_loader.get_phase_data(next_phase_id_str):
                                final_phase_id_for_context = next_phase_id_str
                                print(f"--- Orchestrator [{session_id}]: Transitioning from stage '{current_phase_id_for_logic}' to '{final_phase_id_for_context}'.")
                                
                                if final_phase_id_for_context not in final_completed_tasks_map_for_context:
                                    final_completed_tasks_map_for_context[final_phase_id_for_context] = []
                                elif not isinstance(final_completed_tasks_map_for_context.get(final_phase_id_for_context), list):
                                    final_completed_tasks_map_for_context[final_phase_id_for_context] = []
                                
                                self.session_state_manager.update_session_state(session_id, final_phase_id_for_context, final_completed_tasks_map_for_context)
                            else:
                                print(f"--- Orchestrator [{session_id}]: LLM signaled transition, but next stage '{next_phase_id_str}' not found. Staying.")
                                self.session_state_manager.update_session_state(session_id, current_phase_id_for_logic, final_completed_tasks_map_for_context)
                        except ValueError:
                            print(f"!!! ERROR [Orchestrator - {session_id}]: Cannot increment phase ID '{current_phase_id_for_logic}'. Staying.")
                            self.session_state_manager.update_session_state(session_id, current_phase_id_for_logic, final_completed_tasks_map_for_context)
                else:
                    self.session_state_manager.update_session_state(session_id, current_phase_id_for_logic, final_completed_tasks_map_for_context)

                task_status_prompt_for_output = self.task_formatter.format_task_status_for_prompt(final_phase_id_for_context, final_completed_tasks_map_for_context)
                final_phase_data_def = self.phase_config_loader.get_phase_data(final_phase_id_for_context)
                
                tasks_for_ui_display = self.task_formatter.get_tasks_for_ui_display(final_phase_id_for_context, final_completed_tasks_map_for_context)
                
                print(f"--- Orchestrator [{session_id}]: Preparing tasks for UI. Final Phase ID: {final_phase_id_for_context}")
                # print(f"--- Orchestrator [{session_id}]: Final phase data definition from config: {final_phase_data_def.get('name', 'N/A')}, Tasks: {final_phase_data_def.get('tasks', [])}")

                print(f"--- DEBUG [Orchestrator - {session_id}]: Reached end of try block in get_phase_context, before final return.")
                return {
                    "id": final_phase_id_for_context,
                    "name": final_phase_data_def.get('name', f'Unknown Phase {final_phase_id_for_context}'),
                    "description": final_phase_data_def.get('description', ''),
                    "tasks_for_display": tasks_for_ui_display,
                    "goals": final_phase_data_def.get('goals', []),
                    "task_status_prompt": task_status_prompt_for_output,
                    "completed_tasks_map": final_completed_tasks_map_for_context
                }
        except AttributeError as ae:
            print(f"!!! ATTRIBUTE_ERROR_DEBUG [Orchestrator - {session_id}]: Attribute error in get_phase_context: {ae}")
            if self.app is None and 'app_context' in str(ae):
                 print(f"!!! ATTRIBUTE_ERROR_CONFIRMED [Orchestrator - {session_id}]: self.app was None when trying to access 'app_context'.")
            traceback.print_exc()
            return {"id": "ATTR_ERR", "name": "Attribute Error", "description": str(ae), "tasks_for_display": [], "goals": [], "task_status_prompt": "Lỗi thuộc tính.", "completed_tasks_map": {}}
        except Exception as e:
            print(f"!!! CATASTROPHIC_ERROR_DEBUG [Orchestrator - {session_id}]: Unhandled exception in get_phase_context: {e}")
            traceback.print_exc()
            # Return a minimal error structure if an unexpected exception occurs
            return {"id": "EXCEPTION", "name": "Unhandled Exception", "description": str(e), "tasks_for_display": [], "goals": [], "task_status_prompt": "Lỗi hệ thống.", "completed_tasks_map": {}}

    def get_current_phase_info(self, session_id: str) -> Dict[str, Any]:
        print(f"--- TOP_LEVEL_DEBUG [Orchestrator - {session_id}]: Method get_current_phase_info CALLED.")
        try:
            print(f"--- TOP_LEVEL_DEBUG [Orchestrator - {session_id}]: Inside get_current_phase_info try block. self.app type: {type(self.app)}, self.app is None: {self.app is None}")
            if self.app is None:
                print(f"!!! CRITICAL_ERROR [Orchestrator - {session_id}]: self.app is None in get_current_phase_info! Cannot proceed.")
                return {"id": "APP_INIT_ERROR_INFO", "name": "App Context Error", "tasks_for_display": [], "goals": [], "completed_tasks_map": {}}

            with self.app.app_context():
                print(f"--- DEBUG [Orchestrator - {session_id}]: Entered app_context in get_current_phase_info.")
                current_phase_id_from_db, completed_tasks_map_from_db = self.session_state_manager.get_session_state(session_id)
                phase_data_from_config = self.phase_config_loader.get_phase_data(current_phase_id_from_db)
                
                tasks_for_ui_display = self.task_formatter.get_tasks_for_ui_display(current_phase_id_from_db, completed_tasks_map_from_db)

                return {
                    "id": current_phase_id_from_db,
                    "name": phase_data_from_config.get('name', f'Unknown Phase {current_phase_id_from_db}'),
                    "description": phase_data_from_config.get('description', ''),
                    "tasks_for_display": tasks_for_ui_display,
                    "goals": phase_data_from_config.get('goals', []),
                    "completed_tasks_map": completed_tasks_map_from_db
                }
        except AttributeError as ae:
            print(f"!!! ATTRIBUTE_ERROR_DEBUG [Orchestrator - {session_id}]: Attribute error in get_current_phase_info: {ae}")
            if self.app is None and 'app_context' in str(ae):
                 print(f"!!! ATTRIBUTE_ERROR_CONFIRMED [Orchestrator - {session_id}]: self.app was None when trying to access 'app_context'.")
            traceback.print_exc()
            return {"id": "ATTR_ERR_INFO", "name": "Attribute Error", "description": str(ae), "tasks_for_display": [], "goals": [], "completed_tasks_map": {}}
        except Exception as e:
            print(f"!!! CATASTROPHIC_ERROR_DEBUG [Orchestrator - {session_id}]: Unhandled exception in get_current_phase_info: {e}")
            traceback.print_exc()
            # Return a minimal error structure if an unexpected exception occurs
            return {"id": "EXCEPTION_INFO", "name": "Unhandled Exception", "description": str(e), "tasks_for_display": [], "goals": [], "completed_tasks_map": {}}

    def determine_phase_state_llm(self, session_id: str, conversation_history: ConversationHistory) -> Dict[str, Any]:
        with self.app.app_context():
            try:
                last_known_phase_id_from_db = self.session_state_manager.get_current_phase_id_from_db(session_id)
                print(f"--- Orchestrator (determine_phase_state_llm) [{session_id}]: Last known phase from DB: '{last_known_phase_id_from_db}'.")

                history_log = conversation_history.get_history(session_id=session_id)
                current_phase_def_for_prompt = self.phase_config_loader.get_phase_data(last_known_phase_id_from_db)

                if not history_log:
                    print(f"--- Orchestrator (determine_phase_state_llm) [{session_id}]: No history, using phase '{last_known_phase_id_from_db}'.")
                    current_phase_data_to_return = self.phase_config_loader.get_phase_data(last_known_phase_id_from_db)
                    if not current_phase_data_to_return: 
                         current_phase_data_to_return = self.phase_config_loader.get_phase_data("1") or {}
                    return {"id": last_known_phase_id_from_db, "last_signal": "Bắt đầu", "name": current_phase_data_to_return.get('name', f'Unknown Phase {last_known_phase_id_from_db}'), **current_phase_data_to_return}

                if not current_phase_def_for_prompt:
                    print(f"!!! ERROR [Orchestrator (determine_phase_state_llm) - {session_id}]: Config for phase '{last_known_phase_id_from_db}' not found. Defaulting to '1'.")
                    last_known_phase_id_from_db = "1"
                    self.session_state_manager.update_session_phase_id_in_db(session_id, last_known_phase_id_from_db)
                    current_phase_def_for_prompt = self.phase_config_loader.get_phase_data("1")
                    if not current_phase_def_for_prompt:
                        return {"id": "?", "last_signal": "Error", "name": "Config Error - Phase 1 Missing"}

                current_stage_desc_prompt_simple = f"Stage {last_known_phase_id_from_db}: {current_phase_def_for_prompt.get('name', 'Không rõ')}\n"
                current_stage_desc_prompt_simple += f"Description: {current_phase_def_for_prompt.get('description', 'Không có mô tả')}\n"
                tasks_list = current_phase_def_for_prompt.get('tasks', [])
                current_stage_desc_prompt_simple += "Tasks:\n" + ("\n".join([f"- ({t.get('id')}) {t.get('description')}" for t in tasks_list if isinstance(t, dict)]) + "\n" if tasks_list else "(Không có nhiệm vụ cụ thể cho giai đoạn này)\n")
                goals_list = current_phase_def_for_prompt.get('goals', [])
                current_stage_desc_prompt_simple += "Goals:\n" + ("\n".join([f"- {g}" for g in goals_list]) + "\n" if goals_list else "(Không có mục tiêu cụ thể cho giai đoạn này)\n")

                prompt = STAGE_MANAGER_PROMPT.format(
                    problem=self.problem_description,
                    current_stage_description=current_stage_desc_prompt_simple.strip(),
                    history=self._format_history_for_prompt(history_log)
                )

                print(f"--- Orchestrator (determine_phase_state_llm) [{session_id}]: Requesting phase update from LLM (stage {last_known_phase_id_from_db})...")

                raw_response = self.llm_service.generate(prompt)
                print(f"--- Orchestrator (determine_phase_state_llm) [{session_id}]: Raw LLM Response: {raw_response}")

                parsed_output = None
                # Default to current phase and a neutral signal
                final_determined_phase_id = last_known_phase_id_from_db
                determined_signal_text = "Tiếp tục"

                try:
                    cleaned_llm_response = clean_response(raw_response)
                    parsed_output = parse_json_response(cleaned_llm_response)

                    if parsed_output:
                        signal_data = parsed_output.get("signal")
                        if isinstance(signal_data, list) and len(signal_data) == 2:
                            signal_code, signal_text_from_llm = map(str, signal_data)
                            current_llm_signal = signal_text_from_llm.strip()
                            determined_signal_text = current_llm_signal # Update with LLM signal

                            if current_llm_signal == "Chuyển stage mới" or signal_code == "3":
                                try:
                                    next_phase_int = int(last_known_phase_id_from_db) + 1
                                    next_phase_id_str = str(next_phase_int)
                                    if self.phase_config_loader.get_phase_data(next_phase_id_str):
                                        final_determined_phase_id = next_phase_id_str
                                        determined_signal_text = "Bắt đầu" # Signal for entering a new stage
                                    else:
                                        determined_signal_text = "Đưa ra tín hiệu kết thúc" # No next stage found
                                except ValueError:
                                    print(f"!!! ERROR [Orchestrator (determine_phase_state_llm) - {session_id}]: Cannot increment phase ID '{last_known_phase_id_from_db}'.")
                                    determined_signal_text = "Error" # Keep current phase
                        else:
                            print(f"!!! WARN [Orchestrator (determine_phase_state_llm) - {session_id}]: 'signal' data from LLM not in expected format: {signal_data}. Using default signal.")
                    else:
                        print(f"!!! WARN [Orchestrator (determine_phase_state_llm) - {session_id}]: Failed to parse LLM JSON response. Raw: {raw_response}. Using default signal.")
                
                except Exception as e:
                     print(f"!!! ERROR [Orchestrator (determine_phase_state_llm) - {session_id}]: Error processing LLM response: {e}")
                     traceback.print_exc()
                     determined_signal_text = "Error processing response" # Fallback signal

                if final_determined_phase_id != last_known_phase_id_from_db:
                    self.session_state_manager.update_session_phase_id_in_db(session_id, final_determined_phase_id)

                final_phase_data_to_return = self.phase_config_loader.get_phase_data(final_determined_phase_id)
                if not final_phase_data_to_return:
                    final_phase_data_to_return = {}
                    print(f"!!! WARN [Orchestrator (determine_phase_state_llm) - {session_id}]: Final phase data for '{final_determined_phase_id}' is empty.")

                return {
                    "id": final_determined_phase_id,
                    "last_signal": determined_signal_text,
                    "name": final_phase_data_to_return.get('name', f'Unknown Phase {final_determined_phase_id}'),
                    "description": final_phase_data_to_return.get('description', ''),
                    "tasks": final_phase_data_to_return.get('tasks', []),
                    "goals": final_phase_data_to_return.get('goals', []),
                }
            except Exception as e:
                 print(f"!!! ERROR [Orchestrator (determine_phase_state_llm) - {session_id}]: Failed during phase determination: {e}")
                 traceback.print_exc()
                 return {"id": "?", "last_signal": "Error", "name": "Processing Error"}
