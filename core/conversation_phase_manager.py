# core/conversation_phase_manager.py
import json
import traceback
from typing import Dict, Any, List

from flask import Flask 
from core.conversation_history import ConversationHistory
from services.llm_service import LLMService
from utils.loaders import load_phases_from_yaml
# from utils.loaders import load_phases_from_yaml # If using YAML config

STAGE_MANAGER_PROMPT = """
Bạn là giám sát viên quy trình giải bài toán theo nhóm của các học sinh cấp 3.

Mục tiêu của bạn là phân tích cuộc thảo luận hiện tại của nhóm học sinh, so sánh với mô tả quy trình và các nhiệm vụ cụ thể của từng giai đoạn, để xác định chính xác giai đoạn (stage) mà nhóm đang thực hiện. Cung cấp tín hiệu đầu ra (output signal) rõ ràng và nhất quán về trạng thái của giai đoạn hiện tại (bắt đầu, tiếp tục, kết thúc, hay chuẩn bị chuyển sang giai đoạn mới), nhằm hỗ trợ việc theo dõi tiến độ tổng thể.

Bạn là một chuyên gia phân tích quy trình có kinh nghiệm quan sát các nhóm làm việc cộng tác, đặc biệt là trong bối cảnh giải quyết vấn đề học thuật như Toán học. Bạn rất tỉ mỉ và có phương pháp. Bạn tập trung vào việc lắng nghe (phân tích văn bản hội thoại) và đối chiếu thông tin thu thập được với cấu trúc quy trình đã định sẵn. Bạn không tham gia vào nội dung Toán học, mà chỉ tập trung vào việc xác định vị trí của nhóm trong luồng công việc.

## Nhiệm vụ:
- Nhận thông tin về `Bài toán đang thảo luận`, `Mô tả quá trình và các nhiệm vụ cần thực hiện` (bao gồm định nghĩa rõ ràng các giai đoạn - stages, các nhiệm vụ/mục tiêu của từng giai đoạn), và `Lịch sử cuộc hội thoại`.
- Nghiên cứu kỹ `Mô tả quá trình` để hiểu rõ trình tự các giai đoạn, mục tiêu, nhiệm vụ cụ thể và các dấu hiệu/từ khóa/hành động đặc trưng cho từng giai đoạn.
- Xem xét `Lịch sử cuộc hội thoại`, đặc biệt là các tin nhắn/phát biểu gần đây nhất của các thành viên trong nhóm.
- Xác định Trạng thái giai đoạn hiện tại:
    + Nếu hội thoại cho thấy nhóm vừa bắt đầu thảo luận các nội dung/nhiệm vụ đặc trưng của một giai đoạn MỚI mà trước đó họ chưa làm. Đưa ra tin hiệu `Bắt đầu`.
    + Nếu hội thoại cho thấy nhóm đang tiếp tục thảo luận/thực hiện các nhiệm vụ thuộc về giai đoạn đã được xác định trước đó. Đưa ra tin hiệu `Tiếp tục`.
    + Nếu hội thoại cho thấy nhóm có dấu hiệu rõ ràng đã hoàn thành TẤT CẢ các nhiệm vụ/mục tiêu chính của giai đoạn hiện tại VÀ chưa có dấu hiệu rõ ràng bắt đầu giai đoạn tiếp theo HAY nhóm đang thảo luận những cái khác đi xa với mục tiêu cần đạt. Đưa ra tin hiệu `Đưa ra tín hiệu kết thúc`.
    + Nếu hội thoại cho thấy nhóm vừa kết thúc giai đoạn hiện tại VÀ bắt đầu đề cập/thực hiện các nhiệm vụ của giai đoạn KẾ TIẾP. Đưa ra tin hiệu `Chuyển stage mới`. *Lưu ý: Trạng thái này có thể trùng hoặc ngay sau "Đưa ra tín hiệu kết thúc". Ưu tiên tín hiệu này nếu có dấu hiệu chuyển tiếp rõ ràng.*
- Lưu ý thực hiện từ trên xuống dưới để đưa ra tín hiệu giống một quá trình làm việc

## Kết quả đầu ra:
### Trả về dạng JSON là giải thích ngắn gọn (khoảng 10 từ) và một trong các trường hợp sau như sau:
1. "Bắt đầu" // nếu nhóm vừa bắt đầu một stage mới
2. "Tiếp tục" // nếu nhóm đang trong quá trình thực hiện stage hiện tại
3. "Đưa ra tín hiệu kết thúc" // nếu cần dấu hiệu để nhóm kết thúc chuyển sang stage mới
4. "Chuyển stage mới" // nếu có dấu hiệu rõ ràng chuyển sang stage tiếp theo

### Ví dụ:
Ví dụ 1:
```json
{{
    "explain" : "Cần khuyến khích cả nhóm bắt đầu nhiệm vụ stage mới",
    "signal": ["1", "Bắt đầu"]
}}
Ví dụ 2:
{{
  "explain": "Nhóm vẫn đang thảo luận tích cực trong stage hiện tại",
  "signal": ["2", "Tiếp tục"]
}}

Ví dụ 3:
{{
    "explain" : "Nhóm cơ bản đã thực hiện hết mục tiêu nên khuyến khích chuyển bước mới",
    "signal": ["3", "Đưa ra tín hiệu kết thúc"]
}}

Ví dụ 4:
{{
  "explain": "Nhóm đã hoàn tất giai đoạn hiện tại và đang chuyển bước mới",
  "signal": ["4", "Chuyển stage mới"]
}}

Đầu vào:
Đây là bài toán đang thảo luận:
{problem}
Mô tả chi tiết stage hiện tại:
{current_stage_description}
Lịch sử trò chuyện:
{history}
"""

class ConversationPhaseManager:
    # ... (__init__, _format_history_for_prompt - remain the same) ...
    def __init__(self, phase_config_path: str, problem_description: str, llm_service: LLMService, app_instance):
        self.phases = load_phases_from_yaml(phase_config_path)
        if not self.phases:
            raise ValueError("Failed to load phase configurations.")
        self.problem = problem_description
        self.llm_service = llm_service
        self.app = app_instance 
        print(f"--- PHASE_MGR: Initialized.")

    def _format_history_for_prompt(self, history: List[Dict], count=15) -> str:
        # ... (implementation remains the same) ...
        recent_history = history[-count:]
        lines = []
        for i, event in enumerate(recent_history):
             text = event.get('content', {}).get('text', '(Non-message event)')
             source = event.get('source', 'Unknown')
             lines.append(f"CON#{i+1} {source}: {text}")
        return "\n".join(lines) if lines else "Chưa có hội thoại."

    # <<< Add app context here >>>
    def _determine_phase_state(self, session_id: str, conversation_history: ConversationHistory) -> Dict[str, Any]:
        """Calls LLM to determine the current phase status for the given session."""
        # <<< Get the Flask app instance >>>
        # <<< Wrap context-dependent operations >>>
        with self.app.app_context():
            try:
                # <<< Fetch history within the context >>>
                history_log = conversation_history.get_history(session_id=session_id)
                if not history_log:
                    print(f"--- PHASE_MGR [{session_id}]: No history yet, assuming initial phase '1'.")
                    initial_phase_data = self.phases.get("1", {})
                    return {"id": "1", "last_signal": "Bắt đầu", "name": initial_phase_data.get('name', 'Unknown Phase 1'), **initial_phase_data}

                # Determine current phase ID (using simplification for now)
                current_phase_id_guess = "1"
                last_event = conversation_history.get_last_event(session_id) # DB access
                if last_event and last_event.get('metadata', {}).get('phase_id'):
                     current_phase_id_guess = last_event['metadata']['phase_id']

                current_phase_def = self.phases.get(current_phase_id_guess)
                if not current_phase_def:
                    print(f"!!! ERROR [PhaseManager - {session_id}]: Phase ID '{current_phase_id_guess}' not found.")
                    current_phase_id_guess = "1"
                    current_phase_def = self.phases.get("1", {})
                    if not current_phase_def: return {"id": "?", "last_signal": "Error", "name": "Config Error"}

                # Prepare prompt description (no DB access)
                current_stage_desc_prompt = f"Stage {current_phase_id_guess}: ..." # (rest of formatting)

                prompt = STAGE_MANAGER_PROMPT.format(
                    problem=self.problem,
                    current_stage_description=current_stage_desc_prompt.strip(),
                    history=self._format_history_for_prompt(history_log) # Uses list, no DB access
                )

                print(f"--- PHASE_MGR [{session_id}]: Requesting phase update from LLM (assuming stage {current_phase_id_guess})...")

                determined_phase_id = current_phase_id_guess
                determined_signal = "Tiếp tục"

                # LLM Call (no DB access)
                raw_response = self.llm_service.generate(prompt)
                print(f"--- PHASE_MGR [{session_id}]: Raw LLM Response: {raw_response}")

                # Parsing and transition logic (no DB access)
                # ... (rest of the parsing and transition logic) ...
                try:
                    clean_response = raw_response.strip().replace("```json", "").replace("```", "").replace("{{", "{").replace("}}", "}")
                    parsed_output = json.loads(clean_response)
                    signal_data = parsed_output.get("signal")
                    if not isinstance(signal_data, list) or len(signal_data) != 2: raise ValueError("Invalid 'signal' format.")
                    signal_code, signal_text = signal_data
                    determined_signal = signal_text
                    if determined_signal == "Chuyển stage mới":
                        # ... (transition logic) ...
                        try:
                            next_phase_int = int(determined_phase_id) + 1
                            next_phase_id_str = str(next_phase_int)
                            if next_phase_id_str in self.phases:
                                determined_phase_id = next_phase_id_str
                            else:
                                determined_signal = "Đưa ra tín hiệu kết thúc"
                        except ValueError:
                            determined_signal = "Error"

                except json.JSONDecodeError as e:
                     print(f"!!! ERROR [PhaseManager - {session_id}]: Failed to parse LLM JSON response: {e}")
                except Exception as e:
                     print(f"!!! ERROR [PhaseManager - {session_id}]: Unexpected error during phase update LLM call: {e}")
                     traceback.print_exc()


                # Return results (no DB access)
                final_phase_data = self.phases.get(determined_phase_id, {})
                return {"id": determined_phase_id, "last_signal": determined_signal, "name": final_phase_data.get('name', f'Unknown Phase {determined_phase_id}'), **final_phase_data}

            except Exception as e:
                 # Log error within the context
                 print(f"!!! ERROR [PhaseManager - {session_id}]: Failed during phase determination: {e}")
                 traceback.print_exc()
                 # Return an error state
                 return {"id": "?", "last_signal": "Error", "name": "Processing Error"}


    def get_current_phase(self, session_id: str, conversation_history: ConversationHistory) -> Dict[str, Any]:
        """
        Determines the current phase state for the session using LLM analysis
        and returns the context for that phase.
        """
        # This method now directly calls the context-wrapped determination logic
        return self._determine_phase_state(session_id, conversation_history)