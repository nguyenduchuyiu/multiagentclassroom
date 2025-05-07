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
Phân tích **lịch sử cuộc hội thoại** gần đây của nhóm, đối chiếu với **thông tin về giai đoạn hiện tại** và **bài toán được cung cấp**, để:
1.  Xác định chính xác trạng thái tiến độ của nhóm trong quy trình giải bài toán.
2.  Cung cấp một tín hiệu (`signal`) rõ ràng về trạng thái này (Bắt đầu, Tiếp tục, Cần kết thúc, Chuyển mới) kèm giải thích ngắn gọn (`explain`).
3.  Xác định danh sách ID của các nhiệm vụ (`completed_task_ids`) từ giai đoạn hiện tại mà nhóm dường như đã hoàn thành dựa trên nội dung thảo luận.

## Lưu ý quan trọng:
**Chỉ được coi là hoàn thành giai đoạn hiện tại và chuyển sang giai đoạn tiếp theo khi TẤT CẢ các nhiệm vụ (task) của giai đoạn hiện tại đã hoàn thành** (tức là tất cả ID nhiệm vụ đều nằm trong `completed_task_ids`). Nếu còn bất kỳ nhiệm vụ nào chưa hoàn thành, không được chọn tín hiệu chuyển stage mới.

## Backstory:
Bạn là một chuyên gia phân tích quy trình, tập trung vào việc quan sát và đánh giá luồng công việc cộng tác. Bạn đọc kỹ mô tả các giai đoạn, mục tiêu, và nhiệm vụ của từng bước (bao gồm ID của từng nhiệm vụ) được cung cấp. Bạn lắng nghe cẩn thận (phân tích văn bản hội thoại) để tìm kiếm bằng chứng về việc nhóm đang thực hiện nhiệm vụ nào, đã hoàn thành mục tiêu của giai đoạn hiện tại chưa, và có dấu hiệu chuyển sang giai đoạn tiếp theo hay không. Bạn **không** tham gia giải Toán, chỉ tập trung vào trạng thái quy trình và việc hoàn thành các nhiệm vụ được liệt kê.

## Tasks:
1.  **Tiếp nhận Thông tin:** Nhận các đầu vào sau:
    *   `{problem}`: Nội dung bài toán đang được giải.
    *   `{current_stage_description}`: Mô tả chi tiết về giai đoạn hiện tại, bao gồm ID, tên, mô tả, mục tiêu, và quan trọng nhất là danh sách các nhiệm vụ với ID cụ thể của chúng (ví dụ: "1.1", "1.2"). Đây là nguồn thông tin chính cho "giai đoạn hiện tại".
    *   `{history}`: Lịch sử cuộc hội thoại của nhóm.
2.  **Nghiên cứu Quy trình:** Hiểu rõ mục tiêu và các nhiệm vụ (kèm ID) cần hoàn thành trong **giai đoạn hiện tại này** (dựa trên thông tin từ `{current_stage_description}`).
3.  **Phân tích Hội thoại:** Xem xét `{history}`, đặc biệt là các tin nhắn gần nhất, tìm kiếm bằng chứng (từ khóa, chủ đề thảo luận, câu hỏi, kết quả được nêu) cho thấy nhóm đang:
    *   Bàn luận/thực hiện các nhiệm vụ *cụ thể* (tham chiếu ID nhiệm vụ) của **giai đoạn hiện tại**.
    *   Đã đạt được/hoàn thành các mục tiêu *chính* của **giai đoạn hiện tại**.
    *   Bắt đầu đề cập/thực hiện các nhiệm vụ thuộc về giai đoạn *tiếp theo* (ngay cả khi mô tả giai đoạn hiện tại chưa cập nhật).
    *   Thảo luận lan man, không còn tập trung vào nhiệm vụ của **giai đoạn hiện tại** sau khi có vẻ đã hoàn thành.
4.  **Xác định Trạng thái (Ưu tiên kiểm tra từ trên xuống dưới):**
    *   **(4) Chuyển stage mới:** **Chỉ chọn khi TẤT CẢ các nhiệm vụ của giai đoạn hiện tại đã hoàn thành** (tức là tất cả ID nhiệm vụ đều nằm trong `completed_task_ids`) **VÀ** có bằng chứng rõ ràng nhóm đã *bắt đầu* thảo luận hoặc thực hiện nhiệm vụ của giai đoạn *kế tiếp*. => Chọn tín hiệu `["4", "Chuyển stage mới"]`.
    *   **(3) Đưa ra tín hiệu kết thúc:** Nếu bằng chứng cho thấy nhóm *đã hoàn thành tất cả các nhiệm vụ* của **giai đoạn hiện tại** (tức là tất cả ID nhiệm vụ đều nằm trong `completed_task_ids`) **nhưng chưa có dấu hiệu rõ ràng bắt đầu giai đoạn tiếp theo**, HOẶC thảo luận bắt đầu lan man/dừng lại sau khi đã xong. => Chọn tín hiệu `["3", "Đưa ra tín hiệu kết thúc"]`.
    *   **(1) Bắt đầu:** Nếu bằng chứng cho thấy nhóm *vừa mới bắt đầu* thảo luận/thực hiện các nhiệm vụ đặc trưng của **giai đoạn hiện tại** một cách rõ ràng. => Chọn tín hiệu `["1", "Bắt đầu"]`.
    *   **(2) Tiếp tục:** Nếu không rơi vào các trường hợp trên, tức là nhóm đang *trong quá trình* thảo luận, thực hiện các nhiệm vụ của **giai đoạn hiện tại** một cách tích cực. => Chọn tín hiệu `["2", "Tiếp tục"]`.
5.  **Xác định Nhiệm vụ Hoàn thành (`completed_task_ids`):** Dựa trên `{history}` và phân tích ở bước 3 & 4, liệt kê ID của các nhiệm vụ từ **danh sách nhiệm vụ của giai đoạn hiện tại** mà nhóm đã hoàn thành. Trả về dưới dạng danh sách các chuỗi ID nhiệm vụ (ví dụ: `["1.1", "1.2"]`). Nếu không có, trả về `[]`. Chỉ xem xét các nhiệm vụ của **giai đoạn hiện tại được cung cấp**.

## Output Requirements:
*   Chỉ trả về một đối tượng JSON duy nhất.
*   JSON phải có các khóa sau:
    *   `explain`: Một chuỗi giải thích lý do bạn chọn tín hiệu đó, và có thể đề cập đến các nhiệm vụ đã hoàn thành (nếu có).
    *   `signal`: Một danh sách chứa đúng hai phần tử: một chuỗi số thứ tự (`"1"`, `"2"`, `"3"`, hoặc `"4"`) và chuỗi mô tả trạng thái tương ứng (`"Bắt đầu"`, `"Tiếp tục"`, `"Đưa ra tín hiệu kết thúc"`, `"Chuyển stage mới"`).
    *   `completed_task_ids`: Một danh sách các chuỗi ID của các nhiệm vụ đã được xác định là hoàn thành trong giai đoạn hiện tại.
*   **KHÔNG** bao gồm bất kỳ văn bản nào khác ngoài đối tượng JSON này.

### Ví dụ Định dạng Đầu ra:
```json
{{
    "explain": "Nhóm đã hoàn thành việc tìm hiểu đề bài (nhiệm vụ 1.1) và đang thảo luận về việc chuyển sang lên kế hoạch.",
    "signal": ["3", "Đưa ra tín hiệu kết thúc"],
    "completed_task_ids": ["1.1"]
}}
{{
    "explain": "Nhóm đang tích cực tính đạo hàm cho bước 2 của giai đoạn 3 (nhiệm vụ 3.2). Chưa có nhiệm vụ nào hoàn thành rõ ràng trong lượt này.",
    "signal": ["2", "Tiếp tục"],
    "completed_task_ids": []
}}
{{
    "explain": "Nhóm đã hoàn thành xong bước 1 (Tập xác định - 3.1) và bước 2 (Tính đạo hàm - 3.2) của giai đoạn 3.",
    "signal": ["2", "Tiếp tục"],
    "completed_task_ids": ["3.1", "3.2"]
}}
Input Data:
Bài toán đang thảo luận:
{problem}
Mô tả chi tiết stage hiện tại (ID, tên, mô tả, mục tiêu, danh sách nhiệm vụ với ID của chúng):
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
                for task_idx, task_item in enumerate(phase_data['tasks']):
                    if isinstance(task_item, dict) and 'id' in task_item and 'description' in task_item:
                        task_map[task_item['id']] = task_item['description']
                        processed_tasks.append(task_item)
                    elif isinstance(task_item, str): 
                        print(f"!!! WARN [PhaseManager]: Task in phase {phase_id} is a string, converting. Please update YAML. Task: {task_item}")
                        new_task_id = f"{phase_id}.{task_idx + 1}_auto"
                        task_map[new_task_id] = task_item
                        processed_tasks.append({'id': new_task_id, 'description': task_item})
                    else:
                        print(f"!!! WARN [PhaseManager]: Invalid task format in phase {phase_id}: {task_item}")
                phase_data['_task_map'] = task_map
                phase_data['tasks'] = processed_tasks 
        return phases_cfg

    def _get_session_state(self, session_id: str) -> Tuple[str, Dict[str, List[str]]]:
        """Reads current_phase_id and completed_tasks from DB metadata."""
        db = get_db()
        state_row = db.execute(
            "SELECT current_phase_id, metadata FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()

        if not state_row:
            print(f"!!! WARN [PhaseManager - {session_id}]: Session not found in DB. Defaulting state.")
            return "1", {}

        last_known_phase_id = state_row['current_phase_id'] or "1"

        raw_db_metadata = state_row['metadata'] # Changed variable name for clarity
        metadata = {}
        if raw_db_metadata:
            if isinstance(raw_db_metadata, dict):
                # If it's already a dict, use it directly
                metadata = raw_db_metadata
            elif isinstance(raw_db_metadata, (str, bytes, bytearray)):
                # If it's a string (or bytes), try to parse it
                try:
                    metadata = json.loads(raw_db_metadata)
                except json.JSONDecodeError:
                    print(f"!!! WARN [PhaseManager - {session_id}]: Could not decode metadata JSON: '{raw_db_metadata}'. Defaulting.")
            else:
                # Handle unexpected types
                print(f"!!! WARN [PhaseManager - {session_id}]: Metadata from DB is of unexpected type: {type(raw_db_metadata)}. Defaulting.")
        
        completed_tasks_map = metadata.get("completed_tasks", {})

        return last_known_phase_id, completed_tasks_map

    def _update_session_state(self, session_id: str, new_phase_id_to_set_in_db: str, completed_tasks_map_to_save: Dict[str, List[str]]):
        """Updates current_phase_id and completed_tasks in DB metadata."""
        db = get_db()
        current_metadata_row = db.execute("SELECT metadata FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        
        existing_metadata = {}
        if current_metadata_row and current_metadata_row['metadata']:
            raw_current_db_metadata = current_metadata_row['metadata'] # Changed variable name
            if isinstance(raw_current_db_metadata, dict):
                # If it's already a dict, use it directly
                existing_metadata = raw_current_db_metadata
            elif isinstance(raw_current_db_metadata, (str, bytes, bytearray)):
                # If it's a string (or bytes), try to parse it
                try:
                    existing_metadata = json.loads(raw_current_db_metadata)
                except json.JSONDecodeError:
                    print(f"!!! WARN [PhaseManager - {session_id}]: Could not decode existing metadata JSON during update: '{raw_current_db_metadata}'. Starting fresh.")
            else:
                # Handle unexpected types
                print(f"!!! WARN [PhaseManager - {session_id}]: Existing metadata from DB is of unexpected type during update: {type(raw_current_db_metadata)}. Starting fresh.")

        existing_metadata["current_phase_id"] = new_phase_id_to_set_in_db
        existing_metadata["completed_tasks"] = completed_tasks_map_to_save
        
        try:
            # metadata column expects a dictionary, which will be converted to JSON string by the adapter
            db.execute(
                "UPDATE sessions SET current_phase_id = ?, metadata = ? WHERE session_id = ?",
                (new_phase_id_to_set_in_db, existing_metadata, session_id)
            )
            db.commit()
            print(f"--- PHASE_MGR [{session_id}]: Updated session state in DB - Phase: {new_phase_id_to_set_in_db}, Tasks: {completed_tasks_map_to_save}")
        except Exception as e:
            print(f"!!! ERROR [PhaseManager - {session_id}]: Failed to update session state in DB: {e}")
            traceback.print_exc()
            db.rollback()

    def _format_task_status_for_prompt(self, phase_id_for_status: str, completed_tasks_map: Dict[str, List[str]]) -> str:
        """Formats the task status checklist string for the LLM prompt."""
        phase_def_for_status = self.phases.get(phase_id_for_status)
        if not phase_def_for_status or 'tasks' not in phase_def_for_status:
            return "Không có nhiệm vụ nào được định nghĩa cho giai đoạn này."

        tasks_in_phase = phase_def_for_status.get('tasks', []) 
        completed_ids_for_this_phase = completed_tasks_map.get(phase_id_for_status, []) 

        status_lines = []
        next_task_found = False
        if not tasks_in_phase:
            return "Giai đoạn này không có nhiệm vụ cụ thể nào được liệt kê."
            
        for task_dict in tasks_in_phase:
            task_id = task_dict['id']
            task_desc = task_dict['description']
            is_done = task_id in completed_ids_for_this_phase
            marker = "[X]" if is_done else "[ ]"
            next_marker = ""
            if not is_done and not next_task_found:
                next_marker = " <-- Nhiệm vụ tiếp theo cần tập trung"
                next_task_found = True
            status_lines.append(f"- {marker} ({task_id}) {task_desc}{next_marker}") 

        if not status_lines: return "Không có nhiệm vụ nào cho giai đoạn này."
        return "\n".join(status_lines)

    def mark_task_complete(self, session_id: str, task_id_to_complete: str):
        with self.app.app_context():
            current_phase_id_from_db, completed_tasks_map = self._get_session_state(session_id)
            phase_to_update_tasks_for = current_phase_id_from_db

            if phase_to_update_tasks_for not in self.phases:
                print(f"!!! WARN [PhaseManager - {session_id}]: Phase '{phase_to_update_tasks_for}' (for task '{task_id_to_complete}') not defined in phases config. Skipping task mark.")
                return

            if phase_to_update_tasks_for not in completed_tasks_map:
                completed_tasks_map[phase_to_update_tasks_for] = []

            defined_tasks_for_phase = self.phases[phase_to_update_tasks_for].get('_task_map', {})
            if task_id_to_complete not in defined_tasks_for_phase:
                print(f"!!! WARN [PhaseManager - {session_id}]: Task ID '{task_id_to_complete}' is not a defined task for phase '{phase_to_update_tasks_for}'. Defined tasks: {list(defined_tasks_for_phase.keys())}. Skipping task mark.")
                return

            if task_id_to_complete not in completed_tasks_map[phase_to_update_tasks_for]:
                completed_tasks_map[phase_to_update_tasks_for].append(task_id_to_complete)
                print(f"--- PHASE_MGR [{session_id}]: Marking task '{task_id_to_complete}' as complete for phase '{phase_to_update_tasks_for}'.")
                self._update_session_state(session_id, current_phase_id_from_db, completed_tasks_map)
            else:
                print(f"--- PHASE_MGR [{session_id}]: Task '{task_id_to_complete}' already marked complete for phase '{phase_to_update_tasks_for}'.")

    def get_phase_context(self, session_id: str, conversation_history: ConversationHistory) -> Dict[str, Any]:
        with self.app.app_context(): 
            last_known_phase_id, completed_tasks_map = self._get_session_state(session_id)
            history_log = conversation_history.get_history(session_id=session_id) 

            current_phase_def_for_llm = self.phases.get(last_known_phase_id)
            if not current_phase_def_for_llm:
                print(f"!!! ERROR [PhaseManager - {session_id}]: Config for last known phase '{last_known_phase_id}' not found. Defaulting check to '1'.")
                last_known_phase_id = "1"
                current_phase_def_for_llm = self.phases.get("1", {})
                if not current_phase_def_for_llm: 
                    return {"id": "?", "name": "Config Error", "description": "", "tasks": [], "goals": [], "task_status_prompt": "Lỗi cấu hình giai đoạn."}

            current_stage_desc_prompt = f"Giai đoạn hiện tại (ID: {last_known_phase_id}): {current_phase_def_for_llm.get('name', '')}\n"
            current_stage_desc_prompt += f"Mô tả giai đoạn: {current_phase_def_for_llm.get('description', '')}\n"
            current_stage_desc_prompt += "Danh sách nhiệm vụ của giai đoạn này (ID và mô tả):\n"
            tasks_for_prompt = current_phase_def_for_llm.get('tasks', [])
            if tasks_for_prompt:
                for t in tasks_for_prompt:
                    current_stage_desc_prompt += f"- ({t['id']}) {t['description']}\n"
            else:
                current_stage_desc_prompt += "- (Không có nhiệm vụ cụ thể nào được liệt kê cho giai đoạn này)\n"
            current_stage_desc_prompt += "Mục tiêu của giai đoạn:\n" + "\n".join([f"- {g}" for g in current_phase_def_for_llm.get('goals', [])])

            prompt = STAGE_MANAGER_PROMPT.format(
                problem=self.problem,
                current_stage_description=current_stage_desc_prompt.strip(),
                history=self._format_history_for_prompt(history_log) 
            )

            print(f"--- PHASE_MGR [{session_id}]: Requesting phase signal & task completion from LLM (based on stage {last_known_phase_id})...")
            
            llm_determined_signal_text = "Tiếp tục" 
            # llm_explanation = "Không có giải thích từ LLM." # Keep for potential logging
            completed_task_ids_from_llm = []
            raw_response_for_log = "N/A"

            try:
                raw_response = self.llm_service.generate(prompt)
                raw_response_for_log = raw_response
                print(f"--- PHASE_MGR [{session_id}]: Raw LLM Signal Response: {raw_response}")
                clean_response = raw_response.strip().replace("```json", "").replace("```", "").replace("{{", "{").replace("}}", "}")
                parsed_output = json.loads(clean_response)
                
                signal_data = parsed_output.get("signal")
                # llm_explanation = parsed_output.get("explain", "LLM không cung cấp giải thích.")
                completed_task_ids_from_llm = parsed_output.get("completed_task_ids", [])
                
                if isinstance(signal_data, list) and len(signal_data) == 2:
                    _, signal_text_from_llm = map(str, signal_data) 
                    llm_determined_signal_text = signal_text_from_llm.strip()
                else:
                    print(f"!!! WARN [PhaseManager - {session_id}]: Invalid 'signal' format from LLM: {signal_data}. Defaulting signal to 'Tiếp tục'.")
                
                # print(f"--- PHASE_MGR [{session_id}]: LLM Signal: '{llm_determined_signal_text}'. Tasks completed by LLM: {completed_task_ids_from_llm}. Explanation: {llm_explanation}")
                print(f"--- PHASE_MGR [{session_id}]: LLM Signal: '{llm_determined_signal_text}'. Tasks completed by LLM: {completed_task_ids_from_llm}.")


            except Exception as e:
                print(f"!!! ERROR [PhaseManager - {session_id}]: Failed to get/parse phase signal from LLM: {e}. Raw: {raw_response_for_log}")

            if completed_task_ids_from_llm:
                for task_id in completed_task_ids_from_llm:
                    if isinstance(task_id, str) and task_id.strip():
                        self.mark_task_complete(session_id, task_id.strip())
            
            current_phase_id_for_logic, completed_tasks_map_after_llm_updates = self._get_session_state(session_id)
            
            final_phase_id_for_context = current_phase_id_for_logic 
            final_completed_tasks_map_for_context = completed_tasks_map_after_llm_updates

            if llm_determined_signal_text == "Chuyển stage mới":
                try:
                    next_phase_int = int(current_phase_id_for_logic) + 1
                    next_phase_id_str = str(next_phase_int)
                    if next_phase_id_str in self.phases:
                        final_phase_id_for_context = next_phase_id_str
                        print(f"--- PHASE_MGR [{session_id}]: Transitioning from stage '{current_phase_id_for_logic}' to '{final_phase_id_for_context}'.")
                        
                        if final_phase_id_for_context != current_phase_id_for_logic:
                            if final_phase_id_for_context in final_completed_tasks_map_for_context:
                                print(f"--- PHASE_MGR [{session_id}]: Resetting completed tasks for new phase {final_phase_id_for_context}.")
                            final_completed_tasks_map_for_context[final_phase_id_for_context] = []
                        
                        self._update_session_state(session_id, final_phase_id_for_context, final_completed_tasks_map_for_context)
                    else:
                        print(f"--- PHASE_MGR [{session_id}]: LLM signaled transition, but next stage '{next_phase_id_str}' not found. Staying in '{current_phase_id_for_logic}'.")
                        self._update_session_state(session_id, current_phase_id_for_logic, final_completed_tasks_map_for_context)

                except ValueError:
                    print(f"!!! ERROR [PhaseManager - {session_id}]: Cannot increment phase ID '{current_phase_id_for_logic}'.")
                    self._update_session_state(session_id, current_phase_id_for_logic, final_completed_tasks_map_for_context)
            else:
                self._update_session_state(session_id, current_phase_id_for_logic, final_completed_tasks_map_for_context)

            task_status_prompt = self._format_task_status_for_prompt(final_phase_id_for_context, final_completed_tasks_map_for_context)

            final_phase_data_def = self.phases.get(final_phase_id_for_context, {})

            # Prepare structured tasks for UI display based on the final state
            tasks_for_ui_display = []
            defined_tasks_in_final_phase = final_phase_data_def.get('tasks', [])
            print(f"--- PHASE_MGR [{session_id}]: Preparing tasks for UI. Final Phase ID: {final_phase_id_for_context}")
            print(f"--- PHASE_MGR [{session_id}]: Final phase data definition from config: {final_phase_data_def}")
            print(f"--- PHASE_MGR [{session_id}]: Raw defined tasks for this phase from config: {defined_tasks_in_final_phase}")
            completed_task_ids_in_final_phase = final_completed_tasks_map_for_context.get(final_phase_id_for_context, [])
            
            for task_dict in defined_tasks_in_final_phase:
                tasks_for_ui_display.append({
                    "id": task_dict['id'],
                    "description": task_dict['description'],
                    "completed": task_dict['id'] in completed_task_ids_in_final_phase
                })

            return {
                "id": final_phase_id_for_context,
                "name": final_phase_data_def.get('name', f'Unknown Phase {final_phase_id_for_context}'),
                "description": final_phase_data_def.get('description', ''),
                "tasks_for_display": tasks_for_ui_display,
                "goals": final_phase_data_def.get('goals', []),
                "task_status_prompt": task_status_prompt,
                "completed_tasks_map": final_completed_tasks_map_for_context
            }

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
        """
        Determines the current phase state for the session.
        This is a simplified version, prefer get_phase_context for full updates.
        """
        with self.app.app_context():
            current_phase_id, completed_tasks_map = self._get_session_state(session_id)
            phase_data = self.phases.get(current_phase_id, {})
            
            tasks_for_display = []
            defined_tasks = phase_data.get('tasks', [])
            completed_ids = completed_tasks_map.get(current_phase_id, [])
            for task_dict in defined_tasks:
                tasks_for_display.append({
                    "id": task_dict['id'],
                    "description": task_dict['description'],
                    "completed": task_dict['id'] in completed_ids
                })

            return {
                "id": current_phase_id,
                "name": phase_data.get('name', f'Unknown Phase {current_phase_id}'),
                "description": phase_data.get('description', ''),
                "tasks_for_display": tasks_for_display, # Added for consistency
                "goals": phase_data.get('goals', []),
            }