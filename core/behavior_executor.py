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
                 agent_manager: 'AgentManager'): # Use type hint
        self.interaction_coordinator = interaction_coordinator
        self.problem = problem_description
        self.llm_service = llm_service
        self.agent_manager = agent_manager # To fetch full persona info

    def _format_history_for_prompt(self, history: List[Dict], count=15) -> str:
        """Formats history for the LLM prompt."""
        recent_history = history[-count:]
        lines = []
        for i, event in enumerate(recent_history):
             text = event.get('content', {}).get('text', '(Non-message event)')
             source = event.get('source', 'Unknown')
             # Use name if available (e.g., from agent message content or user message)
             sender_name = event.get('content', {}).get('sender_name', source)
             lines.append(f"CON#{i+1} {sender_name}: {text}")
        return "\n".join(lines) if lines else "Chưa có hội thoại."

    def _generate_final_message(self, agent_id: str, agent_name: str, thought_details: Dict, phase_context: Dict, history: List[Dict]) -> str:
        """Generates the final spoken message using the CLASSMATE_SPEAK prompt."""
        print(f"--- BEHAVIOR_EXECUTOR [{agent_name}]: Generating final message...")

        # Get full persona details
        agent_mind = self.agent_manager.get_agent_mind(agent_id)
        if not agent_mind:
             print(f"!!! ERROR [BehaviorExecutor]: Cannot find AgentMind for ID {agent_id}")
             return "(Lỗi: Không tìm thấy thông tin agent)"
        persona = agent_mind.persona

        # Format phase description
        phase_desc_prompt = f"Stage {phase_context.get('id', 'N/A')}: {phase_context.get('name', '')}\n"
        phase_desc_prompt += f"Description: {phase_context.get('description', '')}\n"
        phase_desc_prompt += "Tasks:\n" + "\n".join([f"- {t}" for t in phase_context.get('tasks', [])]) + "\n"
        phase_desc_prompt += "Goals:\n" + "\n".join([f"- {g}" for g in phase_context.get('goals', [])])

        # Get list of other participant names (AI agents + User)
        all_agent_minds = self.agent_manager.agents.values()
        friend_names = [mind.persona.name for mind in all_agent_minds if mind.persona.agent_id != agent_id]
        # Find the user's name from history (assuming the last user message has sender_name)
        user_name = "User" # Default
        for event in reversed(history):
             if event['source'].startswith('user-') and 'sender_name' in event['content']:
                  user_name = event['content']['sender_name']
                  break
        if user_name not in friend_names:
            friend_names.append(user_name)

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
            history=self._format_history_for_prompt(history)
            # to_user is removed as it wasn't clearly defined how to use it
        )

        # print(f"--- BEHAVIOR_EXECUTOR [{agent_name}] SPEAK PROMPT ---") # DEBUG
        # print(prompt)
        # print("----------------------------------------------------")

        try:
            raw_response = self.llm_service.generate(prompt)
            print(f"--- BEHAVIOR_EXECUTOR [{agent_name}]: Raw LLM Speak Response: {raw_response}")

            # Parse the response: extract text after </think>
            match = re.search(r"<think>.*?</think>\s*(.*)", raw_response, re.DOTALL | re.IGNORECASE)
            if match:
                final_message = match.group(1).strip()
                think_block = match.group(0).split("</think>")[0] + "</think>" # For logging
                print(f"--- BEHAVIOR_EXECUTOR [{agent_name}]: Parsed Think Block: {think_block}")
            else:
                print(f"!!! WARN [BehaviorExecutor - {agent_name}]: Could not find <think> block. Using full response.")
                final_message = raw_response.strip() # Use the whole response as fallback

            if not final_message:
                 print(f"!!! WARN [BehaviorExecutor - {agent_name}]: Generated empty message after parsing. Skipping.")
                 return "" # Return empty string if nothing to say

            return final_message

        except Exception as e:
            print(f"!!! ERROR [BehaviorExecutor - {agent_name}]: Failed during final message generation LLM call: {e}")
            traceback.print_exc()
            return "(Lỗi: Không thể tạo câu trả lời)"


    def _simulate_typing_and_speak(self, agent_id: str, agent_name: str, thought_details: Dict, phase_context: Dict, history: List[Dict]):
        """Generates message, simulates typing, and posts the message."""

        # 1. Generate the actual message using LLM
        final_message = self._generate_final_message(agent_id, agent_name, thought_details, phase_context, history)

        if not final_message:
            # If message generation failed or resulted in empty, just go idle
            self.interaction_coordinator.post_event_to_clients(
                event_type="agent_status",
                source=agent_id,
                content={"status": "idle", "agent_name": agent_name},
                is_internal=True
            )
            return

        # 2. Broadcast typing status
        self.interaction_coordinator.post_event_to_clients(
            event_type="agent_status",
            source=agent_id,
            content={"status": "typing", "agent_name": agent_name},
            is_internal=True
        )

        # 3. Calculate delay based on the *final generated* message
        min_delay = 0.5
        max_delay = 5.0
        delay_per_char = random.uniform(0.03, 0.07)
        typing_delay = min(max_delay, max(min_delay, len(final_message) * delay_per_char))
        print(f"--- BEHAVIOR_EXECUTOR [{agent_name}]: Simulating typing delay: {typing_delay:.2f}s")
        time.sleep(typing_delay)

        # 4. Post the actual message event via InteractionCoordinator
        print(f"--- BEHAVIOR_EXECUTOR [{agent_name}]: Executing 'speak' action with message: {final_message}")
        self.interaction_coordinator.handle_internal_trigger(
            event_type="new_message",
            source=agent_id, # Agent's unique ID is the source
            content={"text": final_message, "sender_name": agent_name} # Include name for display
        )

        # 5. Broadcast idle status after speaking
        self.interaction_coordinator.post_event_to_clients(
             event_type="agent_status",
             source=agent_id,
             content={"status": "idle", "agent_name": agent_name},
             is_internal=True
        )


    def execute(self, agent_id: str, agent_name: str, action: str, selected_thought_details: Dict, phase_context: Dict, history: List[Dict]):
        """Executes the selected action for the agent."""
        print(f"--- BEHAVIOR_EXECUTOR: Received execution request for {agent_name} - Action: {action}")
        if action == "speak":
            if not selected_thought_details:
                print(f"--- BEHAVIOR_EXECUTOR [{agent_name}]: Error - 'speak' action requested without thought details. Skipping.")
                # Ensure agent goes idle if speak fails early
                self.interaction_coordinator.post_event_to_clients(
                     event_type="agent_status", source=agent_id,
                     content={"status": "idle", "agent_name": agent_name}, is_internal=True)
                return

            # Run generation and simulation in a separate thread
            thread = threading.Thread(
                target=self._simulate_typing_and_speak,
                args=(agent_id, agent_name, selected_thought_details, phase_context, history),
                daemon=True
            )
            thread.start()

        elif action == "listen":
            print(f"--- BEHAVIOR_EXECUTOR [{agent_name}]: Executing 'listen' action (no operation).")
            # Set status to idle immediately
            self.interaction_coordinator.post_event_to_clients(
                 event_type="agent_status",
                 source=agent_id,
                 content={"status": "idle", "agent_name": agent_name},
                 is_internal=True
            )
        else:
            print(f"--- BEHAVIOR_EXECUTOR [{agent_name}]: Unknown action '{action}'.")
            # Set status to idle
            self.interaction_coordinator.post_event_to_clients(
                 event_type="agent_status",
                 source=agent_id,
                 content={"status": "idle", "agent_name": agent_name},
                 is_internal=True
            )