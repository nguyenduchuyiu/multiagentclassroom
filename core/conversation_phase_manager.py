# core/conversation_phase_manager.py
import json
import traceback
from typing import Dict, Any, List, Tuple

from flask import Flask 
from core.conversation_history import ConversationHistory
from database.database import get_db
from services.llm_service import LLMService
from utils.loaders import load_phases_from_yaml


STAGE_MANAGER_PROMPT = """
## Role:
Bạn là Giám sát viên Quy trình (Process Supervisor), chuyên theo dõi tiến độ làm việc nhóm của học sinh cấp 3 giải bài toán Toán.

## Goal:
Phân tích **lịch sử cuộc hội thoại (`{history}`)** gần đây của nhóm, đối chiếu với **mô tả giai đoạn hiện tại (`{current_stage_description}`)** và **bài toán (`{problem}`)**, để xác định chính xác trạng thái tiến độ của nhóm trong quy trình giải bài toán. Cung cấp một tín hiệu (`signal`) rõ ràng về trạng thái này (Bắt đầu, Tiếp tục, Cần kết thúc, Chuyển mới) kèm giải thích ngắn gọn (`explain`).

## Backstory:
Bạn là một chuyên gia phân tích quy trình, tập trung vào việc quan sát và đánh giá luồng công việc cộng tác. Bạn đọc kỹ mô tả các giai đoạn, mục tiêu, và nhiệm vụ của từng bước. Bạn lắng nghe cẩn thận (phân tích văn bản hội thoại) để tìm kiếm bằng chứng về việc nhóm đang thực hiện nhiệm vụ nào, đã hoàn thành mục tiêu của giai đoạn hiện tại chưa, và có dấu hiệu chuyển sang giai đoạn tiếp theo hay không. Bạn **không** tham gia giải Toán, chỉ tập trung vào trạng thái quy trình.

## Tasks:
1.  **Tiếp nhận Thông tin:** Nhận `{problem}`, `{current_stage_description}` (bao gồm mục tiêu, nhiệm vụ, có thể cả dấu hiệu nhận biết của giai đoạn hiện tại), và `{history}`.
2.  **Nghiên cứu Quy trình:** Hiểu rõ mục tiêu và các nhiệm vụ cần hoàn thành trong `{current_stage_description}`.
3.  **Phân tích Hội thoại:** Xem xét `{history}`, đặc biệt là các tin nhắn gần nhất, tìm kiếm bằng chứng (từ khóa, chủ đề thảo luận, câu hỏi, kết quả được nêu) cho thấy nhóm đang:
    *   Bàn luận/thực hiện các nhiệm vụ *cụ thể* của giai đoạn mô tả trong `{current_stage_description}`.
    *   Đã đạt được/hoàn thành các mục tiêu *chính* của giai đoạn hiện tại.
    *   Bắt đầu đề cập/thực hiện các nhiệm vụ thuộc về giai đoạn *tiếp theo* (ngay cả khi `{current_stage_description}` chưa cập nhật).
    *   Thảo luận lan man, không còn tập trung vào nhiệm vụ của giai đoạn hiện tại sau khi có vẻ đã hoàn thành.
4.  **Xác định Trạng thái (Ưu tiên kiểm tra từ trên xuống dưới):**
    *   **(4) Chuyển stage mới:** Nếu có bằng chứng rõ ràng nhóm đã *bắt đầu* thảo luận hoặc thực hiện nhiệm vụ của giai đoạn *kế tiếp* (ví dụ: "Vậy bước tiếp theo là...", "Bây giờ mình xét đến...", hoặc thực hiện hành động của bước sau). => Chọn tín hiệu `["4", "Chuyển stage mới"]`.
    *   **(3) Đưa ra tín hiệu kết thúc:** Nếu bằng chứng cho thấy nhóm *đã hoàn thành các mục tiêu/nhiệm vụ chính* của giai đoạn hiện tại (trong `{current_stage_description}`) VÀ *chưa* có dấu hiệu rõ ràng bắt đầu giai đoạn tiếp theo (như ở mục 4), HOẶC thảo luận bắt đầu lan man/dừng lại sau khi có vẻ đã xong. => Chọn tín hiệu `["3", "Đưa ra tín hiệu kết thúc"]`.
    *   **(1) Bắt đầu:** Nếu bằng chứng cho thấy nhóm *vừa mới bắt đầu* thảo luận/thực hiện các nhiệm vụ đặc trưng của giai đoạn hiện tại (trong `{current_stage_description}`) một cách rõ ràng (ví dụ, sau khi kết thúc giai đoạn trước hoặc khi mới bắt đầu thảo luận). => Chọn tín hiệu `["1", "Bắt đầu"]`.
    *   **(2) Tiếp tục:** Nếu không rơi vào các trường hợp trên, tức là nhóm đang *trong quá trình* thảo luận, thực hiện các nhiệm vụ của giai đoạn hiện tại một cách tích cực và chưa hoàn thành hoàn toàn hay chuyển sang giai đoạn mới. => Chọn tín hiệu `["2", "Tiếp tục"]`.

## Output Requirements:
*   Chỉ trả về một đối tượng JSON duy nhất.
*   JSON phải có hai khóa:
    *   `explain`: Một chuỗi giải thích **ngắn gọn** (khoảng 5-15 từ) lý do bạn chọn tín hiệu đó, dựa trên bằng chứng từ hội thoại.
    *   `signal`: Một danh sách chứa đúng hai phần tử: một chuỗi số thứ tự (`"1"`, `"2"`, `"3"`, hoặc `"4"`) và chuỗi mô tả trạng thái tương ứng (`"Bắt đầu"`, `"Tiếp tục"`, `"Đưa ra tín hiệu kết thúc"`, `"Chuyển stage mới"`).
*   **KHÔNG** bao gồm bất kỳ văn bản nào khác ngoài đối tượng JSON này.

### Ví dụ Định dạng Đầu ra:
Ví dụ 1 (Bắt đầu):
```json
{{
    "explain": "Nhóm vừa bắt đầu thảo luận nhiệm vụ đầu tiên của stage.",
    "signal": ["1", "Bắt đầu"]
}}

Ví dụ 2 (Tiếp tục):
{{
    "explain": "Nhóm đang tích cực thực hiện các bước của stage hiện tại.",
    "signal": ["2", "Tiếp tục"]
}}

Ví dụ 3 (Cần kết thúc):

{{
    "explain": "Nhóm đã hoàn thành mục tiêu chính, cần tín hiệu để chuyển bước.",
    "signal": ["3", "Đưa ra tín hiệu kết thúc"]
}}

Ví dụ 4 (Chuyển mới):
{{
    "explain": "Nhóm đã bắt đầu thảo luận sang nhiệm vụ của stage tiếp theo.",
    "signal": ["4", "Chuyển stage mới"]
}}
Input Data:
Bài toán đang thảo luận:
{problem}
Mô tả chi tiết stage hiện tại (mục tiêu, nhiệm vụ):
{current_stage_description}
Lịch sử cuộc hội thoại:
{history}
"""

class ConversationPhaseManager:
    def __init__(self, phase_config_path: str, problem_description: str, llm_service: LLMService, app_instance: Flask):
        self.phases = self._load_and_process_phases(phase_config_path) # Process phases on load
        if not self.phases:
            raise ValueError("Failed to load phase configurations.")
        self.problem = problem_description
        self.llm_service = llm_service
        self.app = app_instance # Store app instance
        print(f"--- PHASE_MGR: Initialized.")

    def _load_and_process_phases(self, filepath: str) -> Dict[str, Dict]:
        """Loads phases and creates a map of task IDs for easy lookup."""
        phases_cfg = load_phases_from_yaml(filepath)
        if not phases_cfg: return {}
        for phase_id, phase_data in phases_cfg.items():
             if 'tasks' in phase_data and isinstance(phase_data['tasks'], list):
                 task_map = {}
                 processed_tasks = []
                 for task in phase_data['tasks']:
                     if isinstance(task, dict) and 'id' in task and 'description' in task:
                         task_map[task['id']] = task['description']
                         processed_tasks.append(task) # Keep original structure if needed elsewhere
                     else:
                          print(f"!!! WARN [PhaseManager]: Invalid task format in phase {phase_id}: {task}")
                 # Store both the map and potentially the original list if needed
                 phase_data['_task_map'] = task_map
                 phase_data['tasks'] = processed_tasks # Store processed tasks back
        return phases_cfg

    def _get_session_state(self, session_id: str) -> Tuple[str, Dict[str, List[str]]]:
        """Reads current_phase_id and completed_tasks from DB metadata."""
        db = get_db()
        state_row = db.execute(
            "SELECT current_phase_id, metadata FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()

        if not state_row:
            print(f"!!! WARN [PhaseManager - {session_id}]: Session not found in DB. Defaulting state.")
            return "1", {} # Default to phase 1, empty completed tasks

        last_known_phase_id = state_row['current_phase_id'] or "1"

        metadata = state_row['metadata'] # Directly use the dict from the row factory
        if metadata is None: # Handle case where metadata might be NULL in DB
             metadata = {}
             
        completed_tasks_map = metadata.get("completed_tasks", {}) # Get the map {"phase_id": ["task_id"]}

        return last_known_phase_id, completed_tasks_map

    def _update_session_state(self, session_id: str, new_phase_id: str, completed_tasks_map: Dict[str, List[str]]):
        """Updates current_phase_id and completed_tasks in DB metadata."""
        db = get_db()
        new_metadata = {
            "status": "active", # Keep other metadata if needed
            "current_phase_id": new_phase_id,
            "completed_tasks": completed_tasks_map
        }
        try:
            db.execute(
                "UPDATE sessions SET current_phase_id = ?, metadata = ? WHERE session_id = ?",
                (new_phase_id, new_metadata, session_id)
            )
            db.commit()
            print(f"--- PHASE_MGR [{session_id}]: Updated session state in DB - Phase: {new_phase_id}")
        except Exception as e:
            print(f"!!! ERROR [PhaseManager - {session_id}]: Failed to update session state in DB: {e}")
            db.rollback()

    def _format_task_status_for_prompt(self, phase_id: str, completed_tasks_map: Dict[str, List[str]]) -> str:
         """Formats the task status checklist string for the LLM prompt."""
         current_phase_def = self.phases.get(phase_id)
         if not current_phase_def or '_task_map' not in current_phase_def:
             return "Không có nhiệm vụ nào được định nghĩa cho giai đoạn này."

         tasks_in_phase = current_phase_def.get('tasks', []) # Get the list of task dicts
         completed_ids_for_phase = completed_tasks_map.get(phase_id, []) # Get completed IDs for *this* phase

         status_lines = []
         next_task_found = False
         for task_dict in tasks_in_phase:
             task_id = task_dict['id']
             task_desc = task_dict['description']
             is_done = task_id in completed_ids_for_phase
             marker = "[X]" if is_done else "[ ]"
             next_marker = ""
             if not is_done and not next_task_found:
                 next_marker = " <-- Nhiệm vụ tiếp theo"
                 next_task_found = True
             status_lines.append(f"- {marker} ({task_id}) {task_desc}{next_marker}") # Include ID for clarity

         if not status_lines: return "Không có nhiệm vụ nào cho giai đoạn này."
         return "\n".join(status_lines)

    # <<< Main method to get phase context including task status >>>
    def get_phase_context(self, session_id: str, conversation_history: ConversationHistory) -> Dict[str, Any]:
        """
        Determines phase signal, handles transitions, updates DB state,
        and returns full context including formatted task status.
        """
        with self.app.app_context(): # Ensure DB operations happen within context
            last_known_phase_id, completed_tasks_map = self._get_session_state(session_id)
            history_log = conversation_history.get_history(session_id=session_id) # Needs context

            current_phase_def = self.phases.get(last_known_phase_id)
            if not current_phase_def:
                print(f"!!! ERROR [PhaseManager - {session_id}]: Config for last known phase '{last_known_phase_id}' not found. Defaulting check to '1'.")
                last_known_phase_id = "1"
                current_phase_def = self.phases.get("1", {})
                if not current_phase_def: return {"id": "?", "signal": "Error", "name": "Config Error", "task_status_prompt": "Error"}

            # Prepare prompt description (uses phase definition, no DB access)
            current_stage_desc_prompt = f"Stage {last_known_phase_id}: {current_phase_def.get('name', '')}\n..." # (Full formatting)
            current_stage_desc_prompt += f"Description: {current_phase_def.get('description', '')}\n"
            # Use processed tasks list
            current_stage_desc_prompt += "Tasks:\n" + "\n".join([f"- ({t['id']}) {t['description']}" for t in current_phase_def.get('tasks', [])]) + "\n"
            current_stage_desc_prompt += "Goals:\n" + "\n".join([f"- {g}" for g in current_phase_def.get('goals', [])])

            prompt = STAGE_MANAGER_PROMPT.format(
                problem=self.problem,
                current_stage_description=current_stage_desc_prompt.strip(),
                history=self._format_history_for_prompt(history_log) # Uses list, no DB access
            )

            print(f"--- PHASE_MGR [{session_id}]: Requesting phase signal from LLM (based on stage {last_known_phase_id})...")

            determined_phase_id = last_known_phase_id # Start assuming current phase
            determined_signal = "Tiếp tục" # Default signal

            # --- LLM Call to Determine Signal ---
            try:
                raw_response = self.llm_service.generate(prompt)
                print(f"--- PHASE_MGR [{session_id}]: Raw LLM Signal Response: {raw_response}")
                clean_response = raw_response.strip().replace("```json", "").replace("```", "").replace("{{", "{").replace("}}", "}")
                parsed_output = json.loads(clean_response)
                signal_data = parsed_output.get("signal")
                if not isinstance(signal_data, list) or len(signal_data) != 2: raise ValueError("Invalid 'signal' format.")
                signal_code, signal_text = signal_data
                determined_signal = signal_text
                print(f"--- PHASE_MGR [{session_id}]: LLM Signal: {determined_signal} ({signal_code})")

            except Exception as e:
                print(f"!!! ERROR [PhaseManager - {session_id}]: Failed to get/parse phase signal from LLM: {e}")
                # Keep determined_signal as "Tiếp tục" (default)

            # --- Phase Transition Logic ---
            new_phase_id = determined_phase_id # Assume no transition initially
            if determined_signal == "Chuyển stage mới":
                try:
                    next_phase_int = int(last_known_phase_id) + 1
                    next_phase_id_str = str(next_phase_int)
                    if next_phase_id_str in self.phases:
                        new_phase_id = next_phase_id_str
                        print(f"--- PHASE_MGR [{session_id}]: Transitioning from stage '{last_known_phase_id}' to '{new_phase_id}'.")
                        # Reset completed tasks for the new phase
                        if new_phase_id in completed_tasks_map:
                             print(f"--- PHASE_MGR [{session_id}]: Resetting completed tasks for new phase {new_phase_id}.")
                             completed_tasks_map[new_phase_id] = []
                        determined_signal = "Bắt đầu" # Signal start of the new phase
                    else:
                        print(f"--- PHASE_MGR [{session_id}]: LLM signaled transition, but next stage '{next_phase_id_str}' not found. Staying in '{last_known_phase_id}'.")
                        determined_signal = "Đưa ra tín hiệu kết thúc" # Signal end of current phase
                except ValueError:
                    print(f"!!! ERROR [PhaseManager - {session_id}]: Cannot increment phase ID '{last_known_phase_id}'.")
                    determined_signal = "Error"

            # --- Update DB State if Phase Changed ---
            if new_phase_id != last_known_phase_id:
                self._update_session_state(session_id, new_phase_id, completed_tasks_map)
            # If phase didn't change, completed_tasks_map retains its state from _get_session_state

            # --- Format Task Status for the FINAL Determined Phase ---
            # Use the *potentially updated* completed_tasks_map
            task_status_prompt = self._format_task_status_for_prompt(new_phase_id, completed_tasks_map)

            # --- Return Context ---
            final_phase_data = self.phases.get(new_phase_id, {})
            return {
                "id": new_phase_id,
                "signal": determined_signal, # Use 'signal' consistently
                "name": final_phase_data.get('name', f'Unknown Phase {new_phase_id}'),
                "description": final_phase_data.get('description', ''),
                "tasks": final_phase_data.get('tasks', []), # Pass processed tasks list
                "_task_map": final_phase_data.get('_task_map', {}), # Pass map if needed
                "goals": final_phase_data.get('goals', []),
                "task_status_prompt": task_status_prompt, # Include formatted status string
                # Add original LLM explanation if needed
                # "signal_explanation": explanation
            }

    # Placeholder for updating task completion - Needs actual logic
    def mark_task_complete(self, session_id: str, task_id_to_complete: str):
         """Explicitly marks a task as complete in the DB state."""
         with self.app.app_context():
            current_phase_id, completed_tasks_map = self._get_session_state(session_id)
            if current_phase_id not in completed_tasks_map:
                completed_tasks_map[current_phase_id] = []

            if task_id_to_complete not in completed_tasks_map[current_phase_id]:
                 completed_tasks_map[current_phase_id].append(task_id_to_complete)
                 print(f"--- PHASE_MGR [{session_id}]: Marking task '{task_id_to_complete}' as complete for phase {current_phase_id}.")
                 self._update_session_state(session_id, current_phase_id, completed_tasks_map)
            else:
                 print(f"--- PHASE_MGR [{session_id}]: Task '{task_id_to_complete}' already marked complete for phase {current_phase_id}.")

    def _format_history_for_prompt(self, history: List[Dict], count=15) -> str:
        recent_history = history[-count:]
        lines = []
        for i, event in enumerate(recent_history):
            text = event.get('content', {}).get('text', '(Non-message event)')
            source_display = event.get('content', {}).get('sender_name', event.get('source', 'Unknown'))
            lines.append(f"CON#{i+1} {source_display}: {text}")
        return "\n".join(lines) if lines else "Chưa có hội thoại."

    def _update_session_phase_in_db(self, session_id: str, new_phase_id: str):
        """Updates the current_phase_id in the sessions table."""
        # Assumes this is called within an app context
        try:
            db = get_db()
            db.execute(
                "UPDATE sessions SET current_phase_id = ? WHERE session_id = ?",
                (new_phase_id, session_id)
            )
            db.commit()
            print(f"--- PHASE_MGR [{session_id}]: Updated session phase in DB to '{new_phase_id}'.")
        except Exception as e:
            print(f"!!! ERROR [PhaseManager - {session_id}]: Failed to update session phase in DB: {e}")
            db.rollback() # Rollback on error

    def _determine_phase_state(self, session_id: str, conversation_history: ConversationHistory) -> Dict[str, Any]:
        """Calls LLM to determine the current phase status and updates DB if needed."""
        # Use the stored app instance
        with self.app.app_context():
            try:
                db = get_db() # Get DB connection within context

                # Get Last Known Phase ID from DB
                session_data = db.execute(
                    "SELECT current_phase_id FROM sessions WHERE session_id = ?", (session_id,)
                ).fetchone()

                last_known_phase_id = "1" # Default
                if session_data and session_data['current_phase_id']:
                    last_known_phase_id = session_data['current_phase_id']
                elif session_data: # Row exists but phase is null
                     print(f"!!! WARN [PhaseManager - {session_id}]: current_phase_id is null in DB. Defaulting to '1'.")
                     self._update_session_phase_in_db(session_id, last_known_phase_id) # Update DB
                else: # Session row doesn't exist? Should not happen if called correctly
                     print(f"!!! ERROR [PhaseManager - {session_id}]: Session data not found in DB. Defaulting phase to '1'.")

                print(f"--- PHASE_MGR [{session_id}]: Last known phase from DB: '{last_known_phase_id}'.")

                # Fetch history (needs context)
                history_log = conversation_history.get_history(session_id=session_id)
                if not history_log:
                    print(f"--- PHASE_MGR [{session_id}]: No history yet, using phase '{last_known_phase_id}'.")
                    current_phase_data = self.phases.get(last_known_phase_id, self.phases.get("1", {}))
                    return {"id": last_known_phase_id, "last_signal": "Bắt đầu", "name": current_phase_data.get('name', 'Unknown Phase'), **current_phase_data}

                current_phase_def = self.phases.get(last_known_phase_id)
                if not current_phase_def:
                    print(f"!!! ERROR [PhaseManager - {session_id}]: Config for phase ID '{last_known_phase_id}' not found. Defaulting check to '1'.")
                    last_known_phase_id = "1"
                    current_phase_def = self.phases.get("1", {})
                    if not current_phase_def:
                        return {"id": "?", "last_signal": "Error", "name": "Config Error"}

                # Prepare prompt description
                current_stage_desc_prompt = f"Stage {last_known_phase_id}: {current_phase_def.get('name', 'Không rõ')}\n"
                current_stage_desc_prompt += f"Description: {current_phase_def.get('description', 'Không có mô tả')}\n"
                tasks_list = current_phase_def.get('tasks', [])
                current_stage_desc_prompt += "Tasks:\n" + ("\n".join([f"- {t}" for t in tasks_list]) + "\n" if tasks_list else "(Không có nhiệm vụ cụ thể cho giai đoạn này)\n")
                goals_list = current_phase_def.get('goals', [])
                current_stage_desc_prompt += "Goals:\n" + ("\n".join([f"- {g}" for g in goals_list]) + "\n" if goals_list else "(Không có mục tiêu cụ thể cho giai đoạn này)\n")

                prompt = STAGE_MANAGER_PROMPT.format(
                    problem=self.problem,
                    current_stage_description=current_stage_desc_prompt.strip(),
                    history=self._format_history_for_prompt(history_log)
                )

                print(f"--- PHASE_MGR [{session_id}]: Requesting phase update from LLM (based on stage {last_known_phase_id})...")

                determined_phase_id = last_known_phase_id
                determined_signal = "Tiếp tục"

                # LLM Call
                raw_response = self.llm_service.generate(prompt)
                print(f"--- PHASE_MGR [{session_id}]: Raw LLM Response: {raw_response}")

                # Parsing and transition logic
                newly_determined_phase_id = determined_phase_id
                try:
                    clean_response = raw_response.strip()
                    if clean_response.startswith("```json"): clean_response = clean_response[7:]
                    if clean_response.endswith("```"): clean_response = clean_response[:-3]
                    clean_response = clean_response.strip().replace("{{", "{").replace("}}", "}")
                    parsed_output = json.loads(clean_response)
                    signal_data = parsed_output.get("signal")
                    if not isinstance(signal_data, list) or len(signal_data) != 2: raise ValueError("Invalid 'signal' format.")
                    signal_code, signal_text = map(str, signal_data)
                    determined_signal = signal_text.strip()

                    if determined_signal == "Chuyển stage mới":
                        try:
                            next_phase_int = int(determined_phase_id) + 1
                            next_phase_id_str = str(next_phase_int)
                            if next_phase_id_str in self.phases:
                                newly_determined_phase_id = next_phase_id_str
                                determined_signal = "Bắt đầu"
                            else:
                                determined_signal = "Đưa ra tín hiệu kết thúc"
                        except ValueError:
                            determined_signal = "Error"
                    determined_phase_id = newly_determined_phase_id

                except Exception as e:
                     print(f"!!! ERROR [PhaseManager - {session_id}]: Error processing LLM response: {e}")
                     determined_phase_id = last_known_phase_id
                     determined_signal = "Tiếp tục"
                     if isinstance(e, json.JSONDecodeError): print(f"Raw response was: {raw_response}")
                     elif not isinstance(e, ValueError): traceback.print_exc()

                # Update DB if determined phase changed from the one we started with
                if determined_phase_id != last_known_phase_id:
                    self._update_session_phase_in_db(session_id, determined_phase_id)

                # Return results for the final determined phase
                final_phase_data = self.phases.get(determined_phase_id, {})
                metadata = {"phase_id": determined_phase_id, "phase_name": final_phase_data.get('name', f'Unknown Phase {determined_phase_id}')}
                return {
                    "id": determined_phase_id,
                    "last_signal": determined_signal,
                    "name": final_phase_data.get('name', f'Unknown Phase {determined_phase_id}'),
                    "metadata": metadata,
                    **final_phase_data
                }

            except Exception as e:
                 print(f"!!! ERROR [PhaseManager - {session_id}]: Failed during phase determination: {e}")
                 traceback.print_exc()
                 return {"id": "?", "last_signal": "Error", "name": "Processing Error"}

    def get_current_phase(self, session_id: str, conversation_history: ConversationHistory) -> Dict[str, Any]:
        """Determines the current phase state for the session."""
        return self._determine_phase_state(session_id, conversation_history)