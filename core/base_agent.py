# base_agent.py
import json
from pprint import pprint
import random
import time
import threading
import traceback
from core.io_handler import DefaultIOHandler
from services.llm_service import LLMService

DEFAULT_PROMPT_TEMPLATE = """
--- System instruction ---:
{system_instruction}

--- Rules ---:
{rules}

--- Tasks:
{tasks}

--- Recent chat history:
{history}

--- Last message:
{last_message}

Hãy phản hồi phù hợp:
"""

class BaseAgent:
    def __init__(self,
                 agent_id: str,
                 event_manager,
                 conversation,
                 system_instruction: str,
                 prompt_template: str = None,
                 io_handler=None,
                 **config):
        self.agent_id = agent_id
        self.agent_name = config.pop('name', agent_id)
        self.event_manager = event_manager
        self.conversation = conversation
        self.system_instruction = system_instruction
        self.tasks = config.pop('tasks', {})
        self._llm_service = LLMService(**config)
        self._lock = threading.RLock()
        self._current_status = "idle"
        self.prompt = ""

        # Prompt template và IO handler (strategy)
        self.prompt_template = prompt_template or DEFAULT_PROMPT_TEMPLATE
        self.io = io_handler or DefaultIOHandler(self.prompt_template)

        if self.event_manager:
            self.event_manager.subscribe_agent(self)

    def _update_status(self, status):
        with self._lock:
            if self._current_status == status:
                return
            self._current_status = status
        self.event_manager.broadcast_agent_status(
            self.agent_id, self.agent_name, status
        )

    def get_status(self):
        with self._lock:
            return self._current_status

    def _think(self, **kwargs):
        # Lấy lịch sử và chuẩn bị dữ liệu đầu vào
        recent_history = self.conversation.get_recent_history()
        if not recent_history:
            return None
        parsed = self.io.parse_input(kwargs, self.conversation)

        # Build prompt và gọi LLM
        prompt = self.io.build_prompt(
            parsed,
            system_instruction=self.system_instruction,
            tasks=self.tasks
        )
        self.prompt = prompt
        print("[Prompt Created]\n")
        print(prompt)
        return self._llm_service.generate(prompt)

    def _decide_action(self, llm_response):
        if not llm_response:
            return None
        chunks = self.io.parse_output(llm_response)
        return chunks if chunks else None

    def process_new_event(self, **kwargs):
        if not self._lock.acquire(blocking=False):
            return
        try:
            self._update_status("thinking")
            llm_response = self._think(**kwargs)
            actionable = self._decide_action(llm_response)

            if actionable:
                self._update_status("typing")
                for msg in actionable:
                    msg = msg.strip()
                    if not msg:
                        continue
                    time.sleep(random.uniform(1, 2))
                    time.sleep(min(len(msg) * random.uniform(0.02, 0.06), 8))
                    if self.get_status() == "typing":
                        ai_msg = self.conversation.add_message(self.agent_name, msg)
                        self.event_manager.broadcast_new_message(ai_msg)
                    else:
                        break
                self._update_status("idle")
            else:
                self._update_status("idle")
        except Exception as e:
            print(f"Error in {self.agent_name}: {e}")
            traceback.print_exc()
            self._update_status("idle")
        finally:
            self._lock.release()

    def cleanup(self):
        if self.event_manager:
            self.event_manager.unsubscribe_agent(self.agent_name)




