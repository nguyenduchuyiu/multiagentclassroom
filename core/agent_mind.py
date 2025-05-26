# core/agent_mind.py
import threading
import json
import traceback
from typing import Dict, Any, Optional, List

from flask import Flask, current_app
from core.persona import Persona
from core.conversation_history import ConversationHistory
from core.stage_management.conversation_phase_orchestrator import ConversationPhaseOrchestrator
from services.llm_service import LLMService
from core.prompt_templates import AGENT_INNER_THOUGHTS_PROMPT



class AgentMind:
    def __init__(self, persona: Persona, problem_description: str, llm_service: LLMService, app_instance: Flask):
        self.persona = persona
        self.problem = problem_description
        self._llm_service = llm_service
        self.app = app_instance # Store app instance
        self._internal_state: Dict[str, Any] = {"thoughts_log": []}
        self._lock = threading.Lock()

    def _format_history_for_prompt(self, history: List[Dict], count=50) -> str:
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

        # Poor thinking
        poor_thinking = ""

        # ai_description
        ai_desc_prompt = f"Role: {self.persona.role}\nGoal: {self.persona.goal}\nBackstory: {self.persona.backstory}\nFunctions: {self.persona.tasks}" # (rest of AI desc)
        
        try:
            prompt = AGENT_INNER_THOUGHTS_PROMPT.format(
                AI_name=self.persona.name,
                problem=self.problem,
                current_stage_description=phase_desc_prompt.strip(),
                task_status_prompt=task_status_prompt,
                AI_description=ai_desc_prompt.strip(),
                previous_thoughts=self._format_previous_thoughts(),
                history=self._format_history_for_prompt(history),
                poor_thinking = poor_thinking
            )
            return prompt
        except KeyError as e:
            print(f"!!! ERROR [AgentMind - {self.persona.name}]: Missing key in AGENT_INNER_THOUGHTS_PROMPT format: {e}")
            return f"Lỗi tạo prompt: Thiếu key {e}"
        except Exception as e:
            print(f"!!! ERROR [AgentMind - {self.persona.name}]: Unexpected error formatting AGENT_INNER_THOUGHTS_PROMPT: {e}")
            return "Lỗi tạo prompt."

    def think(self, session_id: str, triggering_event: Dict, conversation_history: ConversationHistory, phase_manager: ConversationPhaseOrchestrator) -> Optional[Dict[str, Any]]:        
        """Performs the inner thinking process for a specific session."""
        if not self._lock.acquire(blocking=False):
            print(f"--- AGENT_MIND [{self.persona.name} - {session_id}]: Already thinking, skipping.")
            return None

        log_prefix = f"--- AGENT_MIND [{self.persona.name} - {session_id}]"

        # Use the stored app instance
        with self.app.app_context():
            try:
                # print(f"{log_prefix}: Starting thinking process...")
                # Fetch history and phase within context
                recent_history = conversation_history.get_history(session_id=session_id, count=100)
                current_phase_context = phase_manager.get_current_phase_info(session_id)

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
                # print(f"{log_prefix}: Thinking complete. Intention: {action}. Thought: {thought}")
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