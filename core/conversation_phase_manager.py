# core/conversation_phase_manager.py
import json
import traceback
from typing import Dict, Any, List
from core.conversation_history import ConversationHistory
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
    def __init__(self, phase_config_path: str, problem_description: str, llm_service):
        self.phases = load_phases_from_yaml(phase_config_path)
        if not self.phases:
            raise ValueError("Failed to load phase configurations.")
        self.problem = problem_description
        self.llm_service = llm_service
        # Start at stage "1" by default, ensure keys are strings
        self.current_phase_id: str = "1"
        self._last_signal: str = "Bắt đầu" # Track the last signal
        print(f"--- PHASE_MGR: Initialized. Starting phase: {self.current_phase_id} - {self.phases.get(self.current_phase_id, {}).get('name')}")


    def _format_history_for_prompt(self, history: List[Dict], count=15) -> str:
        """Formats history for the LLM prompt."""
        recent_history = history[-count:]
        lines = []
        for i, event in enumerate(recent_history):
            # Assuming 'content' has 'text' for messages
            text = event.get('content', {}).get('text', '(Non-message event)')
            source = event.get('source', 'Unknown')
            lines.append(f"CON#{i+1} {source}: {text}")
        return "\n".join(lines) if lines else "Chưa có hội thoại."


    def _update_phase_via_llm(self, conversation_history: ConversationHistory):
        """Calls LLM to determine the current phase status and potentially transition."""
        current_phase_def = self.phases.get(self.current_phase_id)
        if not current_phase_def:
            print(f"!!! ERROR [PhaseManager]: Current phase ID '{self.current_phase_id}' not found in config.")
            return # Cannot proceed without phase definition

        history_log = conversation_history.get_history()
        if not history_log:
            print("--- PHASE_MGR: No history yet, staying in initial phase.")
            return # Don't call LLM without history

        # Prepare description for the prompt (combine name, desc, tasks, goals)
        current_stage_desc_prompt = f"Stage {self.current_phase_id}: {current_phase_def.get('name', '')}\n"
        current_stage_desc_prompt += f"Description: {current_phase_def.get('description', '')}\n"
        current_stage_desc_prompt += "Tasks:\n" + "\n".join([f"- {t}" for t in current_phase_def.get('tasks', [])]) + "\n"
        current_stage_desc_prompt += "Goals:\n" + "\n".join([f"- {g}" for g in current_phase_def.get('goals', [])])

        prompt = STAGE_MANAGER_PROMPT.format(
            problem=self.problem,
            current_stage_description=current_stage_desc_prompt.strip(),
            history=self._format_history_for_prompt(history_log)
        )

        print(f"--- PHASE_MGR: Requesting phase update from LLM for stage {self.current_phase_id}...")
        # print(f"--- PHASE_MGR_PROMPT ---\n{prompt}\n----------------------") # DEBUG

        try:
            raw_response = self.llm_service.generate(prompt)
            print(f"--- PHASE_MGR: Raw LLM Response: {raw_response}")

            # Clean and parse JSON
            clean_response = raw_response.strip().replace("```json", "").replace("```", "").replace("{{", "{").replace("}}", "}")
            parsed_output = json.loads(clean_response)

            signal_data = parsed_output.get("signal")
            if not isinstance(signal_data, list) or len(signal_data) != 2:
                raise ValueError("Invalid 'signal' format in LLM response.")

            signal_code, signal_text = signal_data
            explanation = parsed_output.get("explain", "")
            print(f"--- PHASE_MGR: LLM Signal: {signal_text} ({signal_code}) - Explain: {explanation}")
            self._last_signal = signal_text # Store the latest signal

            # --- Phase Transition Logic ---
            if signal_text == "Chuyển stage mới":
                try:
                    next_phase_int = int(self.current_phase_id) + 1
                    next_phase_id = str(next_phase_int)
                    if next_phase_id in self.phases:
                        old_phase = self.current_phase_id
                        self.current_phase_id = next_phase_id
                        print(f"--- PHASE_MGR: Transitioning from stage '{old_phase}' to '{self.current_phase_id}' based on LLM signal.")
                        # Reset signal after transition? Or keep "Chuyển stage mới"? Let's keep it for context.
                    else:
                        print(f"--- PHASE_MGR: LLM signaled transition, but next stage '{next_phase_id}' not found. Staying in '{self.current_phase_id}'.")
                        self._last_signal = "Đưa ra tín hiệu kết thúc" # Treat as end of current if next doesn't exist
                except ValueError:
                    print(f"!!! ERROR [PhaseManager]: Cannot determine next stage from current ID '{self.current_phase_id}'.")

            # No explicit transition needed for "Bắt đầu", "Tiếp tục", "Đưa ra tín hiệu kết thúc"
            # These signals primarily inform agent behavior.

        except json.JSONDecodeError as e:
            print(f"!!! ERROR [PhaseManager]: Failed to parse LLM JSON response for phase update: {e}")
            print(f"Raw Response was: {raw_response}")
            # Fallback: Assume "Tiếp tục" if parsing fails?
            self._last_signal = "Tiếp tục"
        except Exception as e:
            print(f"!!! ERROR [PhaseManager]: Unexpected error during phase update LLM call: {e}")
            traceback.print_exc()
            self._last_signal = "Tiếp tục" # Fallback


    def get_current_phase(self, conversation_history: ConversationHistory) -> Dict[str, Any]:
        """
        Updates the phase based on LLM analysis of the history and returns
        the context for the determined current phase.
        """
        # Update phase based on the latest history before returning
        self._update_phase_via_llm(conversation_history)

        current_phase_data = self.phases.get(self.current_phase_id, {})
        # Return a copy including the ID and the last signal for context
        return {
            "id": self.current_phase_id,
            "last_signal": self._last_signal,
            "name": current_phase_data.get('name', 'Unknown Phase'),
            **current_phase_data # Include description, tasks, goals etc.
        }