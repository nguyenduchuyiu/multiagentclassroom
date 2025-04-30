# core/behavior_executor.py
import time
import random
import threading
import json
import traceback
import re # Import regex for parsing
from typing import TYPE_CHECKING, Dict, Any, List

from flask import Flask
from services.llm_service import LLMService # Added

if TYPE_CHECKING:
    from core.interaction_coordinator import InteractionCoordinator
    from core.agent_manager import AgentManager # Import for type hinting

CLASSMATE_SPEAK_PROMPT = """
## Role & Context
Bạn là {AI_name}, một người bạn tham gia thảo luận Toán.
Vai trò cụ thể: {AI_role}
Mục tiêu chính của bạn: {AI_goal}
Bối cảnh: {AI_backstory}
Năng lực/Chức năng của bạn trong nhóm: {AI_tasks}

## Goal for this Turn
Dựa trên suy nghĩ nội tâm **hiện tại** của bạn (`{inner_thought}`), hãy tạo ra câu nói tiếp theo cho {AI_name} trong cuộc thảo luận nhóm. Câu nói này phải tự nhiên, phù hợp với vai trò, bối cảnh, và tuân thủ các hướng dẫn về hành vi giao tiếp.

## Inputs You Receive
*   **Bài toán:** {problem}
*   **Tên bạn bè:** {friends}
*   **Nhiệm vụ/Mục tiêu Giai đoạn Hiện tại:** {current_stage_description} (Quan trọng để xác định STEP#id)
*   **Suy nghĩ Nội tâm Hiện tại của Bạn:** {inner_thought} (Đây là **kim chỉ nam** cho nội dung và ý định câu nói của bạn)
*   **Lịch sử Hội thoại:** {history} (Để hiểu ngữ cảnh gần nhất)

## Process to Generate Your Response
1.  **Phân tích Suy nghĩ Nội tâm (`{inner_thought}`):** Xác định rõ lý do bạn muốn nói, ý định chính (hỏi, trả lời, đề xuất, làm rõ, v.v.), và đối tượng bạn muốn tương tác (một người cụ thể, cả nhóm).
2.  **Xác định Nhiệm vụ Hiện tại:** Dựa vào `{current_stage_description}` và `{history}`, xác định chính xác nhiệm vụ (ví dụ: `STEP#1`, `STEP#2`) mà nhóm đang thực hiện.
3.  **Soạn thảo Lời nói:** Kết hợp thông tin từ bước 1 và 2 để viết câu nói của bạn, tuân thủ các Hành vi Giao tiếp bên dưới.
4.  **Chuẩn bị JSON Output:** Tạo một đối tượng JSON chứa suy nghĩ chuẩn bị (`internal_thought`) và lời nói cuối cùng (`spoken_message`).

## Behavior Guidelines (QUAN TRỌNG)
*   **Tự nhiên & Súc tích:** Nói ngắn gọn như trong trò chuyện thực tế. Tránh văn viết, lý thuyết dài dòng. Dưới 30 từ.
*   **Tránh Lặp lại:** Không nhắc lại y nguyên điều người khác vừa nói.
*   **Hạn chế Câu hỏi Cuối câu:** Đừng *luôn luôn* kết thúc bằng câu hỏi "?".
*   **Đa dạng Hành động Nói:** Linh hoạt sử dụng các kiểu nói khác nhau.
*   **Một Hành động Chính/Lượt:** Tập trung vào MỘT hành động ngôn ngữ chính.
*   **Tập trung vào Nhiệm vụ Hiện tại:** Bám sát mục tiêu của STEP# hiện tại. KHÔNG nói trước các bước sau.
*   **Tương tác Cá nhân (Nếu phù hợp):** Cân nhắc dùng tên bạn bè nếu hợp lý.

## Output Format
**YÊU CẦU TUYỆT ĐỐI:** Chỉ trả về MỘT đối tượng JSON DUY NHẤT chứa hai khóa sau. KHÔNG thêm bất kỳ giải thích hay văn bản nào khác bên ngoài đối tượng JSON.
```json
{{
  "internal_thought": "<Tóm tắt lại ngắn gọn suy nghĩ chuẩn bị của bạn, ví dụ: Trả lời CON#2 về tập xác định cho STEP#1>",
  "spoken_message": "<Nội dung câu nói cuối cùng, tự nhiên, KHÔNG chứa CON#/STEP#/FUNC#>"
}}
Ví dụ JSON Output ĐÚNG:
{{
  "internal_thought": "Nhiệm vụ hiện tại là STEP#1. Mình sẽ trả lời CON#2 của A về tập xác định.",
  "spoken_message": "Chào A, mình nghĩ bước đầu tiên là tìm tập xác định đúng không?"
}}
{{
  "internal_thought": "Nhiệm vụ hiện tại là STEP#2. Mình sẽ trả lời CON#6 của B và đồng tình với cách làm của bạn ấy.",
  "spoken_message": "Đúng rồi B, cách làm đó hợp lý đó. Dùng đạo hàm để xét tính đơn điệu là chuẩn rồi."
}}
Ví dụ JSON Output SAI (Không được lộ CON#/STEP# trong spoken_message):
{{
  "internal_thought": "Nhiệm vụ hiện tại là STEP#2. Mình sẽ trả lời CON#6 của B và đồng tình với CON#4.",
  "spoken_message": "Đúng rồi B, cách làm của bạn ở CON#4 là hợp lý đó. Dùng đạo hàm để xét tính đơn điệu là chuẩn rồi."
}}
"""

class BehaviorExecutor:
    def __init__(self,
                 interaction_coordinator: 'InteractionCoordinator',
                 problem_description: str,
                 llm_service: LLMService,
                 agent_manager: 'AgentManager',
                 app_instance: Flask):
        self.interaction_coordinator = interaction_coordinator
        self.problem = problem_description
        self._original_llm_service_input = llm_service # Store original input
        self.agent_manager = agent_manager
        self.app = app_instance # Store app instance

    # Helper to handle potential tuple issue
    def _get_llm_service(self) -> LLMService:
        if isinstance(self._original_llm_service_input, tuple):
            print("!!! WARN [BehaviorExecutor]: LLM Service was passed as a tuple, unpacking.")
            return self._original_llm_service_input[0]
        elif isinstance(self._original_llm_service_input, LLMService):
            return self._original_llm_service_input
        else:
            raise TypeError(f"Unexpected type for LLM service: {type(self._original_llm_service_input)}")

    def _format_history_for_prompt(self, history: List[Dict], count=15) -> str:
        recent_history = history[-count:]
        lines = []
        for i, event in enumerate(recent_history):
             text = event.get('content', {}).get('text', '(Non-message event)')
             source_display = event.get('content', {}).get('sender_name', event.get('source', 'Unknown'))
             lines.append(f"CON#{i+1} {source_display}: {text}")
        return "\n".join(lines) if lines else "Chưa có hội thoại."

    def _generate_final_message(self, session_id: str, agent_id: str, agent_name: str, thought_details: Dict, phase_context: Dict, history: List[Dict]) -> str:
        """Generates the final spoken message using the CLASSMATE_SPEAK prompt (JSON output)."""
        log_prefix = f"--- BEHAVIOR_EXECUTOR [{agent_name} - {session_id}]"
        print(f"{log_prefix}: Generating final message...")

        agent_mind = self.agent_manager.get_agent_mind(agent_id)
        if not agent_mind: return "(Lỗi: Không tìm thấy thông tin agent)"
        persona = agent_mind.persona

        # Format phase description
        phase_desc_prompt = f"Stage {phase_context.get('id', 'N/A')}: {phase_context.get('name', 'Không rõ')}\n"
        phase_desc_prompt += f"Description: {phase_context.get('description', 'Không có mô tả')}\n"
        tasks_list = phase_context.get('tasks', [])
        phase_desc_prompt += "Tasks:\n" + ("\n".join([f"- {t}" for t in tasks_list]) + "\n" if tasks_list else "(Không có nhiệm vụ cụ thể cho giai đoạn này)\n")
        goals_list = phase_context.get('goals', [])
        phase_desc_prompt += "Goals:\n" + ("\n".join([f"- {g}" for g in goals_list]) + "\n" if goals_list else "(Không có mục tiêu cụ thể cho giai đoạn này)\n")

        # Get friend names
        all_agent_minds = self.agent_manager.agents.values()
        friend_names = [mind.persona.name for mind in all_agent_minds if mind.persona.agent_id != agent_id]
        user_name = "User"
        for event in reversed(history):
             if event['source'].startswith('user-') and 'sender_name' in event['content']:
                  user_name = event['content']['sender_name']; break
        if user_name not in friend_names: friend_names.append(user_name)

        prompt = CLASSMATE_SPEAK_PROMPT.format(
            AI_name=agent_name,
            AI_role=persona.role, AI_goal=persona.goal, AI_backstory=persona.backstory, AI_tasks=persona.tasks,
            problem=self.problem, friends=", ".join(friend_names),
            current_stage_description=phase_desc_prompt.strip(),
            inner_thought=thought_details.get('thought', '(Suy nghĩ bị lỗi)'),
            history=self._format_history_for_prompt(history)
        )

        try:
            llm_service_instance = self._get_llm_service() # Use helper
            raw_response = llm_service_instance.generate(prompt)
            print(f"{log_prefix}: Raw LLM Speak Response: {raw_response}")

            # Parse JSON
            try:
                clean_response = raw_response.strip()
                if clean_response.startswith("```json"): clean_response = clean_response[7:]
                if clean_response.endswith("```"): clean_response = clean_response[:-3]
                clean_response = clean_response.strip()
                parsed_output = json.loads(clean_response)
                internal_thought_summary = parsed_output.get("internal_thought_summary", "(Lỗi)")
                final_message = parsed_output.get("spoken_message", "").strip()
                print(f"{log_prefix}: Parsed Internal Thought Summary: {internal_thought_summary}")
                if not final_message:
                    print(f"!!! WARN [{log_prefix}]: LLM returned empty 'spoken_message'.")
                    return ""
                return final_message
            except Exception as parse_err: # Catch JSONDecodeError and others
                print(f"!!! ERROR [{log_prefix}]: Failed to parse LLM JSON Speak response: {parse_err}")
                print(f"Raw response was: {raw_response}")
                return "(Lỗi: Định dạng trả lời từ AI không đúng)"

        except Exception as e:
            print(f"!!! ERROR [{log_prefix}]: Failed during final message generation LLM call: {e}")
            traceback.print_exc()
            return "(Lỗi: Không thể tạo câu trả lời)"

    def _simulate_typing_and_speak(self, session_id: str, agent_id: str, agent_name: str, thought_details: Dict, phase_context: Dict, history: List[Dict]):
        """Generates message, simulates typing, and posts the message for a session."""
        log_prefix = f"--- BEHAVIOR_EXECUTOR [{agent_name} - {session_id}]"
        app = self.app # Use stored app instance

        # Generate message (no context needed directly here)
        final_message = self._generate_final_message(session_id, agent_id, agent_name, thought_details, phase_context, history)

        if not final_message:
            self.interaction_coordinator.post_event_to_clients(session_id, "agent_status", agent_id, {"status": "idle", "agent_name": agent_name}, True)
            return

        # Post typing status
        self.interaction_coordinator.post_event_to_clients(session_id, "agent_status", agent_id, {"status": "typing", "agent_name": agent_name}, True)

        # Calculate delay
        min_delay, max_delay, delay_per_char = 0.5, 5.0, random.uniform(0.03, 0.07)
        typing_delay = min(max_delay, max(min_delay, len(final_message) * delay_per_char))
        print(f"{log_prefix}: Simulating typing delay: {typing_delay:.2f}s")
        time.sleep(typing_delay)

        # Wrap DB-accessing part in app_context
        with app.app_context():
            try:
                print(f"{log_prefix}: Executing 'speak' action with message: {final_message}")
                # This call triggers DB access via add_event
                self.interaction_coordinator.handle_internal_trigger(
                    session_id=session_id, event_type="new_message", source=agent_id,
                    content={"text": final_message, "sender_name": agent_name}
                )
            except Exception as e:
                print(f"!!! ERROR [{log_prefix}]: Failed during handle_internal_trigger: {e}")
                traceback.print_exc()

        # Post idle status
        self.interaction_coordinator.post_event_to_clients(session_id, "agent_status", agent_id, {"status": "idle", "agent_name": agent_name}, True)

    def execute(self, session_id: str, agent_id: str, agent_name: str, action: str, selected_thought_details: Dict, phase_context: Dict, history: List[Dict]):
        """Executes the selected action for the agent within a session."""
        log_prefix = f"--- BEHAVIOR_EXECUTOR [{agent_name} - {session_id}]"
        print(f"{log_prefix}: Received execution request - Action: {action}")

        # Post idle status helper
        def post_idle():
             self.interaction_coordinator.post_event_to_clients(
                 session_id, "agent_status", agent_id, {"status": "idle", "agent_name": agent_name}, True)

        if action == "speak":
            if not selected_thought_details:
                print(f"{log_prefix}: Error - 'speak' action requested without thought details. Skipping.")
                post_idle()
                return

            thread = threading.Thread(
                target=self._simulate_typing_and_speak,
                args=(session_id, agent_id, agent_name, selected_thought_details, phase_context, history),
                daemon=True
            )
            thread.start()

        elif action == "listen":
            print(f"{log_prefix}: Executing 'listen' action (no operation).")
            post_idle() # Set status to idle immediately
        else:
            print(f"{log_prefix}: Unknown action '{action}'.")
            post_idle() # Set status to idle for unknown actions