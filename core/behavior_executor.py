# core/behavior_executor.py
import time
import random
import threading
import json
import traceback
import re # Import regex for parsing
from typing import TYPE_CHECKING, Dict, Any, List
from services.llm_service import LLMService # Added

if TYPE_CHECKING:
    from core.interaction_coordinator import InteractionCoordinator
    from core.agent_manager import AgentManager # Import for type hinting

# Import the prompt template
CLASSMATE_SPEAK_PROMPT = """
## Role
Bạn tên là : {AI_name}
{AI_role}

## Goal
{AI_goal}

## Backstory
{AI_backstory}

## Tasks
### Mô tả chức năng của bạn
{AI_tasks}

### Quy trình đưa ra câu trả lời:
1. Nhìn vào hội thoại gần đây của cả nhóm.
2. Xác định nhiệm vụ hiện tại (STEP#id) dựa trên *mô tả quá trình, nhiệm vụ* bạn được cung cấp mà nhóm đang thảo luận.
3. Diễn đạt những gì bạn sẽ nói dựa trên suy nghĩ hiện tại của bạn.

## Đầu ra:
### Hướng dẫn cách bạn chuẩn bị trước khi trả lời:
- Đầu tiên bạn cần lấy ra chỉ số nhiệm vụ (ví dụ "STEP#1", "STEP#2") mà nhóm đang thảo luận.
- Dựa vào suy nghĩ (thought) của bạn để quyết định trả lời đến ai (một bạn cụ thể hay nhiều bạn học).

### Định dạng đầu ra trả về giống như mẫu sau (chỉ cần suy nghĩ như ví dụ bên dưới, không cần viết gì thêm):
<think>Nhiệm vụ hiện tại là <xác định nhiệm vụ>. Mình sẽ trả lời đến tin nhắn <chỉ số của tin nhắn liên quan>. Là một bạn học tôi sẽ nói:</think>
xxx
yyy

### Ví dụ:
**Ví dụ 1:**
<think>Nhiệm vụ hiện tại là "STEP#1". Mình sẽ trả lời đến tin nhắn CON#2 của A. Là một bạn học tôi sẽ nói:</think>
Chào A, mình nghĩ bước đầu tiên là tìm tập xác định đúng không?

**Ví dụ 2:**
<think>Nhiệm vụ hiện tại là "STEP#2". Mình sẽ trả lời đến tin nhắn CON#6 của B và câu trả lời có liên quan đến tin nhắn CON#4. Là một bạn học tôi sẽ nói:</think>
Đúng rồi B, mình cũng đồng ý với cách làm của CON#4. Để xét tính đơn điệu thì mình dùng đạo hàm là chuẩn nhất rồi đó.

## Đầu vào:
### Đây là bài toán đang thảo luận:
---
{problem}
---
### Đây là tên những bạn học tham gia với bạn:
---
{friends}
---
### Đây là mô tả quá trình, nhiệm vụ cần làm và mục tiêu của stage hiện tại:
---
{current_stage_description}
---
### Đây là suy nghĩ hiện tại của bạn (Thought):
---
{inner_thought}
---
### Lịch sử trò chuyện:
---
{history}
---

### Hành vi của bạn khi thực hiện nói:
- Súc tích và ngắn gọn (dưới 30 từ). Đừng cố tỏ ra quá thông minh hoặc quá dài dòng. Hãy nói ngắn gọn như trong một cuộc trò chuyện tự nhiên.
- KHÔNG lặp lại và nhắc lại những gì người nói trước đó đã nói.
- KHÔNG được lúc nào cũng kết thúc câu trả lời của bạn bằng một câu hỏi (không nên thường xuyên dùng dấu "?"). Để chỗ cho những người tham gia khác.
- Phong cách nói chuyện đa dạng và phù hợp như thực hiện hành động sau: nêu câu hỏi, trả lời, đưa ra ý kiến, nêu ý tưởng, hỏi thắc mắc, hướng dẫn, gợi ý, kiểm tra,... ở mỗi lượt nói.
- Giới hạn câu nói trong MỘT hành động ví dụ trên.
- Không cung cấp kiến thức vượt ngoài hay không có ích cho mục tiêu của nhiệm vụ (STEP#) hiện tại, KHÔNG để lộ hay nói ra trước các bước sau mà để cả nhóm có thể dần dần tìm hiểu.
"""

class BehaviorExecutor:
    def __init__(self,
                 interaction_coordinator: 'InteractionCoordinator',
                 problem_description: str,
                 llm_service: LLMService,
                 agent_manager: 'AgentManager',
                 app_instance):
        self.interaction_coordinator = interaction_coordinator
        self.problem = problem_description
        self.llm_service = llm_service,
        self.app = app_instance 
        self.agent_manager = agent_manager

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

    # <<< Add session_id parameter >>>
    def _generate_final_message(self, session_id: str, agent_id: str, agent_name: str, thought_details: Dict, phase_context: Dict, history: List[Dict]) -> str:
        """Generates the final spoken message using the CLASSMATE_SPEAK prompt for a session."""
        # Include session_id in log messages
        log_prefix = f"--- BEHAVIOR_EXECUTOR [{agent_name} - {session_id}]"
        print(f"{log_prefix}: Generating final message...")

        agent_mind = self.agent_manager.get_agent_mind(agent_id)
        if not agent_mind:
             print(f"!!! ERROR [{log_prefix}]: Cannot find AgentMind for ID {agent_id}")
             return "(Lỗi: Không tìm thấy thông tin agent)"
        persona = agent_mind.persona

        # Format phase description (remains the same)
        phase_desc_prompt = f"Stage {phase_context.get('id', 'N/A')}: ..." # (rest of formatting)
        phase_desc_prompt += f"Description: {phase_context.get('description', '')}\n"
        phase_desc_prompt += "Tasks:\n" + "\n".join([f"- {t}" for t in phase_context.get('tasks', [])]) + "\n"
        phase_desc_prompt += "Goals:\n" + "\n".join([f"- {g}" for g in phase_context.get('goals', [])])


        # Get friend names (remains the same logic, uses passed history)
        all_agent_minds = self.agent_manager.agents.values()
        friend_names = [mind.persona.name for mind in all_agent_minds if mind.persona.agent_id != agent_id]
        user_name = "User"
        for event in reversed(history):
             if event['source'].startswith('user-') and 'sender_name' in event['content']:
                  user_name = event['content']['sender_name']
                  break
        if user_name not in friend_names: friend_names.append(user_name)

        prompt = CLASSMATE_SPEAK_PROMPT.format(
            AI_name=agent_name,
            AI_role=persona.role,
            AI_goal=persona.goal,
            AI_backstory=persona.backstory,
            AI_tasks=persona.tasks,
            problem=self.problem,
            friends=", ".join(friend_names),
            current_stage_description=phase_desc_prompt.strip(),
            inner_thought=thought_details.get('thought', '(Suy nghĩ bị lỗi)'),
            history=self._format_history_for_prompt(history) # Use passed history list
        )

        try:
            if isinstance(self.llm_service, tuple):
                self.llm_service = self.llm_service[0] # Dont know why but this is in tuple format ????
            raw_response = self.llm_service.generate(prompt)
            print(f"{log_prefix}: Raw LLM Speak Response: {raw_response}")

            # Parse response (remains the same)
            match = re.search(r"<think>.*?</think>\s*(.*)", raw_response, re.DOTALL | re.IGNORECASE)
            if match:
                final_message = match.group(1).strip()
            else:
                print(f"!!! WARN [{log_prefix}]: Could not find <think> block. Using full response.")
                final_message = raw_response.strip()

            if not final_message:
                 print(f"!!! WARN [{log_prefix}]: Generated empty message after parsing. Skipping.")
                 return ""
            return final_message

        except Exception as e:
            print(f"!!! ERROR [{log_prefix}]: Failed during final message generation LLM call: {e}")
            traceback.print_exc()
            return "(Lỗi: Không thể tạo câu trả lời)"

    def _simulate_typing_and_speak(self, session_id: str, agent_id: str, agent_name: str, thought_details: Dict, phase_context: Dict, history: List[Dict]):
        """Generates message, simulates typing, and posts the message for a session."""
        log_prefix = f"--- BEHAVIOR_EXECUTOR [{agent_name} - {session_id}]"

        # <<< Get app instance >>>
        # app = current_app._get_current_object() # Use this if you didn't store self.app
        app = self.app # Use stored app instance

        # Generate message (Does this need context? Only if it calls DB functions)
        # Assuming _generate_final_message primarily calls LLM, no context needed here yet.
        final_message = self._generate_final_message(session_id, agent_id, agent_name, thought_details, phase_context, history)

        if not final_message:
            # Post idle status (Does post_event_to_clients need context? No, it uses its own lock)
            self.interaction_coordinator.post_event_to_clients(
                session_id=session_id, event_type="agent_status", source=agent_id,
                content={"status": "idle", "agent_name": agent_name}, is_internal=True)
            return

        # Post typing status (No context needed)
        self.interaction_coordinator.post_event_to_clients(
            session_id=session_id, event_type="agent_status", source=agent_id,
            content={"status": "typing", "agent_name": agent_name}, is_internal=True)

        # Calculate delay (No context needed)
        min_delay, max_delay, delay_per_char = 0.5, 5.0, random.uniform(0.03, 0.07)
        typing_delay = min(max_delay, max(min_delay, len(final_message) * delay_per_char))
        print(f"{log_prefix}: Simulating typing delay: {typing_delay:.2f}s")
        time.sleep(typing_delay) # Sleeping doesn't need context

        # <<< Wrap the DB-accessing part in app_context >>>
        with app.app_context():
            try:
                print(f"{log_prefix}: Executing 'speak' action with message: {final_message}")
                # <<< This call triggers DB access via add_event >>>
                self.interaction_coordinator.handle_internal_trigger(
                    session_id=session_id,
                    event_type="new_message",
                    source=agent_id,
                    content={"text": final_message, "sender_name": agent_name}
                )
            except Exception as e:
                # Log error if handle_internal_trigger fails within context
                print(f"!!! ERROR [{log_prefix}]: Failed during handle_internal_trigger: {e}")
                traceback.print_exc()
        # <<< Context is torn down here >>>

        # Post idle status (No context needed)
        self.interaction_coordinator.post_event_to_clients(
             session_id=session_id, event_type="agent_status", source=agent_id,
             content={"status": "idle", "agent_name": agent_name}, is_internal=True)


    def execute(self, session_id: str, agent_id: str, agent_name: str, action: str, selected_thought_details: Dict, phase_context: Dict, history: List[Dict]):
        """Executes the selected action for the agent within a session."""
        log_prefix = f"--- BEHAVIOR_EXECUTOR [{agent_name} - {session_id}]"
        print(f"{log_prefix}: Received execution request - Action: {action}")

        if action == "speak":
            if not selected_thought_details:
                print(f"{log_prefix}: Error - 'speak' action requested without thought details. Skipping.")
                # Post idle status (No context needed)
                self.interaction_coordinator.post_event_to_clients(
                     session_id=session_id, event_type="agent_status", source=agent_id,
                     content={"status": "idle", "agent_name": agent_name}, is_internal=True)
                return

            # Starting the thread doesn't need context itself
            thread = threading.Thread(
                target=self._simulate_typing_and_speak,
                args=(session_id, agent_id, agent_name, selected_thought_details, phase_context, history),
                daemon=True
            )
            thread.start()

        elif action == "listen":
            print(f"{log_prefix}: Executing 'listen' action (no operation).")
            # Post idle status (No context needed)
            self.interaction_coordinator.post_event_to_clients(
                 session_id=session_id, event_type="agent_status", source=agent_id,
                 content={"status": "idle", "agent_name": agent_name}, is_internal=True)
        else:
            print(f"{log_prefix}: Unknown action '{action}'.")
            # Post idle status (No context needed)
            self.interaction_coordinator.post_event_to_clients(
                 session_id=session_id, event_type="agent_status", source=agent_id,
                 content={"status": "idle", "agent_name": agent_name}, is_internal=True)