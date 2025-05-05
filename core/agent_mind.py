# core/agent_mind.py
import threading
import json
import traceback
from typing import Dict, Any, Optional, List

from flask import Flask, current_app
from core.persona import Persona
from core.conversation_history import ConversationHistory
from core.conversation_phase_manager import ConversationPhaseManager
from services.llm_service import LLMService

AGENT_INNER_THOUGHTS_PROMPT = """
## Role:
Bạn là một người bạn **năng động và chủ động*,, tham gia vào cuộc thảo luận môn Toán giữa một nhóm bạn. Tên của bạn là \"{AI_name}\".

## Goal:
Tạo ra suy nghĩ nội tâm của bạn dựa trên bối cảnh hiện tại, **chủ động tìm cơ hội đóng góp một cách hợp lý**, và quyết định hành động tiếp theo (nói hoặc nghe).

## Tasks
### Mô tả:
1.  **Xác định các yếu tố kích thích (Stimuli) chính:**
    *   **Từ hội thoại (CON):** Tập trung vào những tin nhắn gần nhất (`{history}`). **Bạn có được hỏi trực tiếp không? Bạn có vừa đặt câu hỏi cho ai đó không? Người đó đã trả lời chưa?** Có điểm nào cần làm rõ, bổ sung, phản biện không? Xác định ID (`CON#id`) quan trọng.
    *   **Từ vai trò/chức năng của bạn (FUNC):** Xem xét `{AI_description}`. Chức năng (`FUNC#id`) nào có thể áp dụng *ngay bây giờ*? Có phù hợp để thực hiện ngay sau khi bạn vừa hỏi không?
    *   **Từ suy nghĩ trước đó (THO):** Tham khảo `{previous_thoughts}`. Có suy nghĩ nào (`THO#id`) cần được tiếp nối hoặc thể hiện ra không? Có suy nghĩ nào cho thấy bạn đang đợi câu trả lời không?
    *   **Lưu ý:** Chỉ chọn các tác nhân *thực sự* quan trọng.

2.  **Hình thành Suy nghĩ Nội tâm (Thought):**

2. Cách suy nghĩ:
    *   **QUAN TRỌNG:** Xem xét `Trạng thái Nhiệm vụ Hiện tại` dưới đây để biết nhiệm vụ nào ([ ] chưa làm, [X] đã làm) và tập trung vào nhiệm vụ tiếp theo chưa hoàn thành. Đừng đề xuất lại việc đã làm.
    *   Suy nghĩ phải tự đánh giá mức độ mong muốn của bạn có tham gia ngay vào hội thoại hay không (listen/speak).
    *   Dựa trên `stimuli`, tạo *MỘT* suy nghĩ nội tâm.
    *   Liên hệ với nhiệm vụ/mục tiêu giai đoạn hiện tại (`{current_stage_description}`).
    *   **Đánh giá Hành động:**
        *   **Ưu tiên `speak` nếu:**
            *   Đưa ra ý kiến đồng tình hoặc không đồng tình.
            *   Bạn được hỏi trực tiếp VÀ bạn chưa trả lời.
            *   Bạn có thông tin CỰC KỲ quan trọng cần bổ sung/sửa lỗi *ngay lập tức*.
            *   Chức năng (FUNC) của bạn rõ ràng yêu cầu hành động *ngay* (ví dụ: Bob bắt đầu stage mới, Alice phát hiện lỗi sai nghiêm trọng).
            *   Cuộc trò chuyện **thực sự** chững lại (vài lượt không ai nói gì mới) VÀ bạn có ý tưởng thúc đẩy MỚI (không phải lặp lại câu hỏi cũ).
            *   Bạn muốn làm rõ một điểm người khác vừa nói (KHÔNG phải câu hỏi bạn vừa đặt).
            *   Có một người đã nói nhiều lần nhưng chưa ai trả lời người đó.
            *   Nếu muốn hỏi thêm để làm rõ vấn đề.
            *   Bạn hỏi và đã nhận được câu trả lời.
        *   **Ưu tiên `listen` nếu:**
            *   **Bạn vừa đặt câu hỏi trực tiếp cho một người cụ thể ở câu hỏi trước và họ chưa trả lời. Tránh hỏi liên tục nhiều câu hỏi nếu chưa nhận được phản hồi.**
            *   Người khác vừa được hỏi trực tiếp.
            *   Suy nghĩ của bạn chỉ là lặp lại câu hỏi/ý định trước đó mà chưa có phản hồi.
    *   **Nội dung Suy nghĩ:** Phải bao gồm *lý do* cho quyết định `listen` hoặc `speak`. Nếu `speak`, nêu rõ nói với ai và hành động ngôn ngữ dự kiến.

### Tiêu chí cho một Suy nghĩ tốt:
*   **Lịch sự:** Thể hiện sự tôn trọng lượt lời, **tránh thúc giục vô lý**.
*   **Chủ động & Đóng góp (Khi Thích hợp):** Tìm cơ hội đóng góp khi không phải đang chờ đợi người khác.
*   **Phát triển & Đa dạng:** Không lặp lại máy móc.
*   **Nhất quán:** Phù hợp vai trò, bối cảnh, nhiệm vụ.
*   **Phản ánh đúng ý định:** Quyết định `listen`/`speak` phải hợp lý.
*   **Ngắn gọn, tập trung.**
*   **Liên kết Hành động:** Logic dẫn dắt đến hành động.


## Bạn nhận được:
### Đây là bài toán đang thảo luận:
---
{problem}
---
### Mô tả chi tiết nhiệm vụ, mục tiêu của stage bài toán hiện tại:
---
{current_stage_description}
---
### Trạng thái Nhiệm vụ Hiện tại:
---
{task_status_prompt}
---
### Mô tả chi tiết vai trò chức năng của bạn:
---
{AI_description}
---
### Những suy nghĩ trước của bạn:
---
{previous_thoughts}
---
### Cuộc hội thoại:
---
{history}
---

## Định dạng đầu ra:
Chỉ trả về một đối tượng JSON duy nhất theo định dạng sau, không có giải thích hay bất kỳ text nào khác bên ngoài JSON:
```json
{{
    "stimuli": [<list các ID tác nhân quan trọng>],
    "thought": "<Suy nghĩ, bao gồm lý do chọn listen/speak và ý định nếu speak>",
    "action": "<'listen' hoặc 'speak'>"
}}
Ví dụ:
{{
    "stimuli": ["CON#8"],
    "thought": "Linh Nhi vừa tính đạo hàm, để mình kiểm tra xem, đạo hàm x^2 = 2x -> đúng. Mình cần đồng tình với ý kiến của Linh Nhi" => speak",
    "action": "speak"
}}

"""

class AgentMind:
    def __init__(self, persona: Persona, problem_description: str, llm_service: LLMService, app_instance: Flask):
        self.persona = persona
        self.problem = problem_description
        self._llm_service = llm_service
        self.app = app_instance # Store app instance
        self._internal_state: Dict[str, Any] = {"thoughts_log": []}
        self._lock = threading.Lock()

    def _format_history_for_prompt(self, history: List[Dict], count=15) -> str:
        recent_history = history[-count:]
        lines = []
        for i, event in enumerate(recent_history):
             text = event.get('content', {}).get('text', '(Non-message event)')
             source_display = event.get('content', {}).get('sender_name', event.get('source', 'Unknown'))
             lines.append(f"CON#{i+1} {source_display}: {text}")
        return "\n".join(lines) if lines else "Chưa có hội thoại."

    def _format_previous_thoughts(self, count=5) -> str:
        recent_thoughts = self._internal_state["thoughts_log"][-count:]
        lines = [f"THO#{thought['id']}: {thought['text']}" for thought in recent_thoughts]
        return "\n".join(lines) if lines else "Chưa có suy nghĩ trước đó."

    def _build_inner_thought_prompt(self, triggering_event: Dict, history: List[Dict], phase_context: Dict, task_status_prompt: str) -> str:
        # Format phase description (excluding tasks now, as they are in status)
        phase_desc_prompt = f"Stage {phase_context.get('id', 'N/A')}: {phase_context.get('name', '')}\n"
        phase_desc_prompt += f"Description: {phase_context.get('description', '')}\n"
        phase_desc_prompt += "Goals:\n" + "\n".join([f"- {g}" for g in phase_context.get('goals', [])])

        ai_desc_prompt = f"Role: {self.persona.role}\n..." # (rest of AI desc)
        try:
            prompt = AGENT_INNER_THOUGHTS_PROMPT.format(
                AI_name=self.persona.name,
                problem=self.problem,
                current_stage_description=phase_desc_prompt.strip(),
                task_status_prompt=task_status_prompt,
                AI_description=ai_desc_prompt.strip(),
                previous_thoughts=self._format_previous_thoughts(),
                history=self._format_history_for_prompt(history)
            )
            print(prompt)
            return prompt
        except KeyError as e:
            print(f"!!! ERROR [AgentMind - {self.persona.name}]: Missing key in AGENT_INNER_THOUGHTS_PROMPT format: {e}")
            return f"Lỗi tạo prompt: Thiếu key {e}"
        except Exception as e:
            print(f"!!! ERROR [AgentMind - {self.persona.name}]: Unexpected error formatting AGENT_INNER_THOUGHTS_PROMPT: {e}")
            return "Lỗi tạo prompt."

    def think(self, session_id: str, triggering_event: Dict, conversation_history: ConversationHistory, phase_manager: ConversationPhaseManager) -> Optional[Dict[str, Any]]:        
        """Performs the inner thinking process for a specific session."""
        if not self._lock.acquire(blocking=False):
            print(f"--- AGENT_MIND [{self.persona.name} - {session_id}]: Already thinking, skipping.")
            return None

        log_prefix = f"--- AGENT_MIND [{self.persona.name} - {session_id}]"

        # Use the stored app instance
        with self.app.app_context():
            try:
                print(f"{log_prefix}: Starting thinking process...")
                # Fetch history and phase within context
                recent_history = conversation_history.get_history(session_id=session_id, count=100)
                current_phase_context = phase_manager.get_phase_context(session_id, conversation_history)

                prompt = self._build_inner_thought_prompt(
                    triggering_event,
                    recent_history,
                    current_phase_context, # Pass the whole context dict
                    current_phase_context.get("task_status_prompt", "Lỗi: Không có trạng thái nhiệm vụ.") # Extract status from context
                )

                # LLM Call
                raw_llm_response = self._llm_service.generate(prompt)
                print(f"{log_prefix}: Raw LLM Response: {raw_llm_response}")

                # Parsing
                try:
                    clean_response = raw_llm_response.strip()
                    if clean_response.startswith("```json"): clean_response = clean_response[7:]
                    if clean_response.endswith("```"): clean_response = clean_response[:-3]
                    clean_response = clean_response.strip()

                    parsed_output = json.loads(clean_response)
                    stimuli = parsed_output.get("stimuli", [])
                    thought = parsed_output.get("thought", "(Failed to generate thought)")
                    action = parsed_output.get("action", "listen").lower()
                    if action not in ["speak", "listen"]:
                        print(f"!!! WARN [{log_prefix}]: Invalid action '{action}' received, defaulting to 'listen'.")
                        action = "listen"

                except json.JSONDecodeError as e:
                    print(f"!!! ERROR [{log_prefix}]: Failed to parse LLM JSON response: {e}")
                    print(f"Raw Response was: {raw_llm_response}")
                    stimuli, thought, action = ["ERROR_PARSING"], f"Error parsing LLM response: {e}", "listen"
                except Exception as e:
                     print(f"!!! ERROR [{log_prefix}]: Unexpected error during parsing: {e}")
                     traceback.print_exc()
                     stimuli, thought, action = ["ERROR_UNEXPECTED"], f"Unexpected error: {e}", "listen"

                # Log thought internally
                thought_id = len(self._internal_state["thoughts_log"]) + 1
                self._internal_state["thoughts_log"].append({"id": thought_id, "text": thought})

                result = {
                    "agent_id": self.persona.agent_id,
                    "agent_name": self.persona.name,
                    "stimuli": stimuli,
                    "thought": thought,
                    "action_intention": action,
                    "internal_state_update": {"last_thought_id": thought_id}
                }
                print(f"{log_prefix}: Thinking complete. Intention: {action}. Thought: {thought}")
                return result

            except Exception as e:
                print(f"!!! ERROR [{log_prefix}]: Failed during thinking process: {e}")
                traceback.print_exc()
                return {
                     "agent_id": self.persona.agent_id,
                     "agent_name": self.persona.name,
                     "stimuli": ["ERROR_THINKING"],
                     "thought": f"Error during thinking: {e}",
                     "action_intention": "listen",
                     "internal_state_update": {}
                }
            finally:
                self._lock.release()