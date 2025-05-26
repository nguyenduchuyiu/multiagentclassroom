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
from utils.helpers import parse_output
from core.prompt_templates import CLASSMATE_SPEAK_PROMPT

if TYPE_CHECKING:
    from core.interaction_coordinator import InteractionCoordinator
    from core.agent_manager import AgentManager # Import for type hinting



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
        # print(f"{log_prefix}: Generating final message...")

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
                final_message = parse_output(raw_response)
                if not final_message:
                    print(f"!!! WARN [{log_prefix}]: LLM returned empty 'spoken_message'.")
                    return ""
                return final_message
            except Exception as parse_err: # Catch JSONDecodeError and others
                print(f"!!! ERROR [{log_prefix}]: Failed to parse LLM JSON Speak response: {parse_err}")
                print(f"Raw response was: {raw_response}")
                return "..."

        except Exception as e:
            print(f"!!! ERROR [{log_prefix}]: Failed during final message generation LLM call: {e}")
            traceback.print_exc()
            return "🤓"

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
        # print(f"{log_prefix}: Simulating typing delay: {typing_delay:.2f}s")
        time.sleep(typing_delay)

        # Wrap DB-accessing part in app_context
        with app.app_context():
            try:
                # print(f"{log_prefix}: Executing 'speak' action with message: {final_message}")
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
        # print(f"{log_prefix}: Received execution request - Action: {action}")

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