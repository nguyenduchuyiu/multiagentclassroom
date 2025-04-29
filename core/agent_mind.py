# core/agent_mind.py
import threading
import json
import traceback
from typing import Dict, Any, Optional, List
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
    def __init__(self, persona: Persona, problem_description: str, llm_service: LLMService):
        self.persona = persona
        self.problem = problem_description
        self._llm_service = llm_service
        # Store previous thoughts with IDs
        self._internal_state: Dict[str, Any] = {"thoughts_log": []} # List of {"id": thought_id, "text": thought_text}
        self._lock = threading.Lock()
        
    def _format_history_for_prompt(self, history: List[Dict], count=15) -> str:
        """Formats history for the LLM prompt, adding CON# IDs."""
        recent_history = history[-count:]
        lines = []
        for i, event in enumerate(recent_history):
            text = event.get('content', {}).get('text', '(Non-message event)')
            source = event.get('source', 'Unknown')
            # Get sender name if available, otherwise use source ID
            sender_name = event.get('content', {}).get('sender_name', source)
            lines.append(f"CON#{i+1} {sender_name}: {text}") # Use 1-based indexing for prompt
        return "\n".join(lines) if lines else "Chưa có hội thoại."

    def _format_previous_thoughts(self, count=5) -> str:
        """Formats previous thoughts for the LLM prompt, adding THO# IDs."""
        recent_thoughts = self._internal_state["thoughts_log"][-count:]
        lines = [f"THO#{thought['id']}: {thought['text']}" for thought in recent_thoughts]
        return "\n".join(lines) if lines else "Chưa có suy nghĩ trước đó."


    def _build_inner_thought_prompt(self, triggering_event: Dict, history: List[Dict], phase_context: Dict) -> str:
        # Phase description for the prompt
        phase_desc_prompt = f"Stage {phase_context.get('id', 'N/A')}: {phase_context.get('name', '')}\n"
        phase_desc_prompt += f"Description: {phase_context.get('description', '')}\n"
        phase_desc_prompt += "Tasks:\n" + "\n".join([f"- {t}" for t in phase_context.get('tasks', [])]) + "\n"
        phase_desc_prompt += "Goals:\n" + "\n".join([f"- {g}" for g in phase_context.get('goals', [])])

        # Agent description combines role, goal, backstory, tasks from Persona
        ai_desc_prompt = f"Role: {self.persona.role}\n"
        ai_desc_prompt += f"Goal: {self.persona.goal}\n"
        ai_desc_prompt += f"Backstory: {self.persona.backstory}\n"
        ai_desc_prompt += f"Functions/Tasks:\n{self.persona.tasks}" # Assumes tasks are pre-formatted with FUNC#

        prompt = AGENT_INNER_THOUGHTS_PROMPT.format(
            AI_name=self.persona.name,
            problem=self.problem,
            current_stage_description=phase_desc_prompt.strip(),
            AI_description=ai_desc_prompt.strip(),
            previous_thoughts=self._format_previous_thoughts(),
            history=self._format_history_for_prompt(history)
            # poor_thinking is removed as it was likely a placeholder in the original prompt
        )
        return prompt

    def think(self, triggering_event: Dict, conversation_history: ConversationHistory, phase_manager: ConversationPhaseManager) -> Optional[Dict[str, Any]]:
        """Performs the inner thinking process using the AGENT_INNER_THOUGHTS prompt."""
        if not self._lock.acquire(blocking=False):
            print(f"--- AGENT_MIND [{self.persona.name}]: Already thinking, skipping.")
            return None

        try:
            print(f"--- AGENT_MIND [{self.persona.name}]: Starting thinking process...")
            # 1. Get necessary context
            recent_history = conversation_history.get_history(count=20)
            # Get the latest phase context, triggering phase update if necessary
            current_phase_context = phase_manager.get_current_phase(conversation_history)

            # 2. Build Prompt using the specific template
            prompt = self._build_inner_thought_prompt(triggering_event, recent_history, current_phase_context)
            # print(f"--- AGENT_MIND [{self.persona.name}] PROMPT ---") # DEBUG
            # print(prompt)
            # print("-------------------------------------")

            # 3. Call LLM
            raw_llm_response = self._llm_service.generate(prompt)
            print(f"--- AGENT_MIND [{self.persona.name}]: Raw LLM Response: {raw_llm_response}")

            # 4. Parse Output (JSON with stimuli, thought, action)
            try:
                clean_response = raw_llm_response.strip().replace("```json", "").replace("```", "")
                parsed_output = json.loads(clean_response)
                stimuli = parsed_output.get("stimuli", [])
                thought = parsed_output.get("thought", "(Failed to generate thought)")
                action = parsed_output.get("action", "listen").lower()
                if action not in ["speak", "listen"]:
                    print(f"!!! WARN [AgentMind - {self.persona.name}]: Invalid action '{action}' received, defaulting to 'listen'.")
                    action = "listen"

            except json.JSONDecodeError as e:
                print(f"!!! ERROR [AgentMind - {self.persona.name}]: Failed to parse LLM JSON response: {e}")
                print(f"Raw Response was: {raw_llm_response}")
                stimuli = ["ERROR_PARSING"]
                thought = f"Error parsing LLM response: {e}"
                action = "listen"
            except Exception as e:
                print(f"!!! ERROR [AgentMind - {self.persona.name}]: Unexpected error during parsing: {e}")
                stimuli = ["ERROR_UNEXPECTED"]
                thought = f"Unexpected error: {e}"
                action = "listen"

            # 5. Log the thought internally
            thought_id = len(self._internal_state["thoughts_log"]) + 1
            self._internal_state["thoughts_log"].append({"id": thought_id, "text": thought})

            # 6. Return result structure matching expected output
            result = {
                "agent_id": self.persona.agent_id,
                "agent_name": self.persona.name,
                "stimuli": stimuli,
                "thought": thought, # This is the inner thought text
                "action_intention": action, # Changed key name for consistency downstream
                # No potential_message here, it's generated later by CLASSMATE_SPEAK
                "internal_state_update": {"last_thought_id": thought_id} # Example state update
            }
            print(f"--- AGENT_MIND [{self.persona.name}]: Thinking complete. Intention: {action}. Thought: {thought}")
            return result

        except Exception as e:
            print(f"!!! ERROR [AgentMind - {self.persona.name}]: Failed during thinking process: {e}")
            traceback.print_exc()
            return { # Return a failure state
                "agent_id": self.persona.agent_id,
                "agent_name": self.persona.name,
                "stimuli": ["ERROR_THINKING"],
                "thought": f"Error during thinking: {e}",
                "action_intention": "listen",
                "internal_state_update": {}
            }
        finally:
            self._lock.release()