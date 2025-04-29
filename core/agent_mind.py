# core/agent_mind.py
import threading
import json
import traceback
from typing import Dict, Any, Optional, List

from flask import current_app
from core.persona import Persona
from core.conversation_history import ConversationHistory
from core.conversation_phase_manager import ConversationPhaseManager
from services.llm_service import LLMService

# Import the prompt template
AGENT_INNER_THOUGHTS_PROMPT = """
## Role:
Bạn là một người bạn tham gia vào cuộc thảo luận môn Toán giữa một nhóm bạn. Tên của bạn là \"{AI_name}\".

## Goal:
Tạo ra suy nghĩ của bạn dựa vào thời điểm hiện tại (lịch sử hội thoại, ai vừa nói).

## Backstory:
Khi tham gia hội thoại nhiều người nói, bạn sẽ *suy nghĩ trước* mình sẽ nên thực hiện gì khi phân tích tình hình hiện tại của nhóm. Bạn sẽ quyết định rằng tại thời điểm này mình có nên tham gia vào không hay giữ im lặng vì người khác nói sẽ phù hợp hơn mình.

## Tasks
### Mô tả:
1. Xác định những yếu tố, tác nhân làm ảnh hưởng đến suy nghĩ hiện tại:
- Tác nhân đến từ hội thoại hiện tại (Conversation hay CON):
    + Đây là yếu có có *ảnh hưởng nhất* đến suy nghĩ của bạn, đặc biệt là tin nhắn mới nhất;
    + Nhiệm vụ phần này của bạn là xác định những tin nhắn là tác nhân chính. (Xác định CON#id trong đó id là chỉ số thứ tự)
- Tác nhân đến từ chức năng của bạn khi thảo luận (Function hay FUNC):
    + Đây là yếu tố ảnh hưởng đến hành vi trong suy nghĩ của bạn.
    + Bạn sẽ được cung cấp FUNC của bạn, nhiệm vụ là xác định tại thời điểm này nên thực hiện MỘT chức năng nào. (Xác định 1 FUNC#id)
- Tác nhân đến từ những suy nghĩ trước đó (Thought hay THO):
    + Yếu tố này sẽ ảnh hưởng đến cách bạn phát triển suy nghĩ nội tại của mình thông qua quá trình trao đổi;
    + Hãy xác định những THO#id trước đó nào ảnh hưởng việc điều chỉnh suy nghĩ của bạn.

2. Cách suy nghĩ:
- Hình thành MỘT suy nghĩ của bạn tại thời điểm hiện tại bao gồm: hội thoại VÀ nhiệm vụ (STEP#id) của stage bài toán nhóm đang thực hiện.
- Suy nghĩ phải dựa trên các tác nhân mà bạn xác định là quan trọng.
- Suy nghĩ phải tự đánh giá mức độ mong muốn của bạn có tham gia ngay vào hội thoại hay không:
    + listen: ở đây bạn thấy mình không thích hợp để nói ngay vì bạn học khác sẽ nên nói hay suy nghĩ của mình là chưa cần thiết, bạn sẽ nghe và chờ lượt khác.
    + speak: ở đây bạn thấy được mình cần phải nói vì nó sẽ có ảnh hưởng đến sự tự nhiên của quá trình thảo luận hay bạn cần nêu ngay một thông tin rất quan trọng.
- Mỗi suy nghĩ nên ngắn gọn, khoảng 15-20 từ.

### Tiêu chí để đưa ra một suy nghĩ tốt:
- Đảm bảo những suy nghĩ này đa dạng và khác biệt, mỗi suy nghĩ là duy nhất và không phải là sự lặp lại của một suy nghĩ khác. Vì suy nghĩ của bạn sẽ PHÁT TRIỂN theo thời gian khi tham gia thảo luận.
- Đảm bảo các suy nghĩ nhất quán với bối cảnh đã được cung cấp cho bạn.
- Suy nghĩ phản ánh đúng mức độ mong muốn tham gia của bạn. Không ép buộc lúc nào cũng phải nói luôn.
- Nếu bạn mong muốn nói luôn, trong suy nghĩ của bạn phải xác định đến việc nói với ai (một người hay nhiều người) và thực hiện hành động gì.
- Phù hợp với nhiệm vụ trong stage bài toán đang thực hiện.

## QUAN TRỌNG: Chỉ lấy ra các tác nhân hiện có mà bạn nhận được, và KHÔNG nhất thiết phải lấy đủ 3 loại tác nhân trên mà dựa vào bối cảnh chọn ra nguồn tác nhân hợp lý nhất.

## Bạn nhận được:
### Đây là bài toán đang thảo luận:
---
{problem}
---
### Mô tả chi tiết nhiệm vụ, mục tiêu của stage bài toán hiện tại:
---
{current_stage_description}
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
Trả về JSON với định dạng sau:
```json
{{
    "stimuli": [<list các tác nhân hiện có>], # các tác nhân quan trọng trong các loại "CON#", "FUNC#" hoặc "THO#"
    "thought": "<suy nghĩ>", # nếu bạn muốn "speak" hay "listen" hãy cũng bày tỏ vì sao bạn muốn như vậy.
    "action": "<listen or speak>" # trả về "listen" hoặc "speak" tùy theo mức độ mong muốn tham gia của bạn.
}}
"""

class AgentMind:
    def __init__(self, persona: Persona, problem_description: str, llm_service: LLMService, app_instance):
        self.persona = persona
        self.problem = problem_description
        self._llm_service = llm_service,
        self.app = app_instance 
        self._internal_state: Dict[str, Any] = {"thoughts_log": []}
        self._lock = threading.Lock()

    def _format_history_for_prompt(self, history: List[Dict], count=15) -> str:
        # ... (implementation remains the same) ...
        recent_history = history[-count:]
        lines = []
        for i, event in enumerate(recent_history):
             text = event.get('content', {}).get('text', '(Non-message event)')
             source = event.get('source', 'Unknown')
             sender_name = event.get('content', {}).get('sender_name', source)
             lines.append(f"CON#{i+1} {sender_name}: {text}")
        return "\n".join(lines) if lines else "Chưa có hội thoại."

    def _format_previous_thoughts(self, count=5) -> str:
        # ... (implementation remains the same) ...
        recent_thoughts = self._internal_state["thoughts_log"][-count:]
        lines = [f"THO#{thought['id']}: {thought['text']}" for thought in recent_thoughts]
        return "\n".join(lines) if lines else "Chưa có suy nghĩ trước đó."

    def _build_inner_thought_prompt(self, triggering_event: Dict, history: List[Dict], phase_context: Dict) -> str:
        phase_desc_prompt = f"Stage {phase_context.get('id', 'N/A')}: {phase_context.get('name', '')}\n..." # (rest of formatting)
        ai_desc_prompt = f"Role: {self.persona.role}\n..." # (rest of formatting)
        prompt = AGENT_INNER_THOUGHTS_PROMPT.format(
            AI_name=self.persona.name,
            problem=self.problem,
            current_stage_description=phase_desc_prompt.strip(),
            AI_description=ai_desc_prompt.strip(),
            previous_thoughts=self._format_previous_thoughts(),
            history=self._format_history_for_prompt(history)
        )
        return prompt


    def think(self, session_id: str, triggering_event: Dict, conversation_history: ConversationHistory, phase_manager: ConversationPhaseManager) -> Optional[Dict[str, Any]]:
        if not self._lock.acquire(blocking=False):
            print(f"--- AGENT_MIND [{self.persona.name} - {session_id}]: Already thinking, skipping.")
            return None

        log_prefix = f"--- AGENT_MIND [{self.persona.name} - {session_id}]"

        # <<< Wrap context-dependent operations >>>
        with self.app.app_context():
            try:
                print(f"{log_prefix}: Starting thinking process...")
                # <<< These operations now happen within the context >>>
                recent_history = conversation_history.get_history(session_id=session_id, count=20)
                current_phase_context = phase_manager.get_current_phase(session_id, conversation_history)

                prompt = self._build_inner_thought_prompt(triggering_event, recent_history, current_phase_context)

                # LLM call itself doesn't usually need app context, but keep it inside for simplicity
                if isinstance(self._llm_service, tuple):
                    self._llm_service = self._llm_service[0] # Dont know why but this is in tuple format ????
                raw_llm_response = self._llm_service.generate(prompt)
                print(f"{log_prefix}: Raw LLM Response: {raw_llm_response}")

                # <<< Parsing happens within the context >>>
                try:
                    clean_response = raw_llm_response.strip().replace("```json", "").replace("```", "")
                    parsed_output = json.loads(clean_response)
                    stimuli = parsed_output.get("stimuli", [])
                    thought = parsed_output.get("thought", "(Failed to generate thought)")
                    action = parsed_output.get("action", "listen").lower()
                    if action not in ["speak", "listen"]: action = "listen"
                except json.JSONDecodeError as e:
                    print(f"!!! ERROR [{log_prefix}]: Failed to parse LLM JSON response: {e}")
                    stimuli, thought, action = ["ERROR_PARSING"], f"Error parsing LLM response: {e}", "listen"
                except Exception as e:
                     print(f"!!! ERROR [{log_prefix}]: Unexpected error during parsing: {e}")
                     stimuli, thought, action = ["ERROR_UNEXPECTED"], f"Unexpected error: {e}", "listen"

                # <<< State update (if needed) happens within the context >>>
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
                # <<< Error logging happens within the context >>>
                print(f"!!! ERROR [{log_prefix}]: Failed during thinking process: {e}")
                traceback.print_exc()
                # Return error structure outside the context if needed, but it's simpler here
                return {
                     "agent_id": self.persona.agent_id,
                     "agent_name": self.persona.name,
                     "stimuli": ["ERROR_THINKING"],
                     "thought": f"Error during thinking: {e}",
                     "action_intention": "listen",
                     "internal_state_update": {}
                }
            # <<< Context automatically torn down here >>>
            # <<< Lock released outside the context >>>
            finally:
                self._lock.release()