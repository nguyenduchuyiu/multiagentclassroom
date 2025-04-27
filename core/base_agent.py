# base_agent.py
import json
import random
import time
import threading # Import threading
from services.llm_service import LLMService


class BaseAgent:
    def __init__(self, agent_id: str, event_manager, conversation, system_instruction:str, **config):
        self.agent_id = agent_id
        self.agent_name = config.pop('name', agent_id)
        self.event_manager = event_manager
        self.conversation = conversation
        self.system_instruction = system_instruction
        self.tasks = config.pop('tasks', {})
        self._llm_service = LLMService(**config) # Use the correct model name
        self._lock = threading.RLock() # Use Reentrant Lock
        self._current_status = "idle"
        self.prompt = ""
        # --- Đăng ký agent với EventManager ---
        if self.event_manager:
            self.event_manager.subscribe_agent(self)

    def _update_status(self, status):
        # Now this is safe even if called from process_new_event
        with self._lock:
            # Check if status actually changed to avoid redundant updates/broadcasts
            if self._current_status == status:
                return # No change, do nothing
            self._current_status = status
            print(f"AGENT STATUS: {self.agent_name} is now {status}") # Log the change

        # Broadcast outside the lock to avoid holding agent lock while potentially
        # waiting for event manager lock (reduces potential deadlock scenarios further, though unlikely here)
        self.event_manager.broadcast_agent_status(self.agent_id, self.agent_name, status)


    def get_status(self):
         with self._lock: # RLock is safe here too
              return self._current_status

    def _create_prompt(self, recent_history, **kwargs):
        """Tạo prompt cụ thể cho LLM. Sẽ được override bởi lớp con."""
        history_text = "\n".join([f"{msg['sender']}: {msg['text']}" for msg in recent_history])
        last_message = recent_history[-1] if recent_history else None

        prompt = f"--- System instruction ---:\n"
        prompt += f"{self.system_instruction}\n"
        prompt += "--- Tasks ---\n"
        for idx, (task_name, task_info) in enumerate(self.tasks.items()):
            prompt += f"{idx+1}. {task_name}: {task_info['description']}\n"
        prompt += "--- Lịch sử chat gần đây ---\n"
        prompt += f"{history_text}\n"
        prompt += "--- Kết thúc lịch sử ---\n"
        if last_message:
            prompt += f"Tin nhắn mới nhất từ {last_message['sender']} là: {last_message['text']}\n"
        
        self.prompt = prompt.format(**kwargs)
        print(self.prompt)
    

    def _decide_action(self, llm_response):
        """Quyết định có phản hồi hay không dựa trên kết quả LLM."""
        # Logic đơn giản: nếu không phải NO_RESPONSE và không rỗng thì trả lời
        print("raw ", llm_response)
        llm_response = json.loads(llm_response)
        if llm_response:
            if llm_response["response"].strip().upper() != "NO_RESPONSE":
                return llm_response["response"].strip()
        return None

    def _think(self, **kwargs):
        """Quá trình suy nghĩ: lấy history, tạo prompt, gọi LLM."""
        recent_history = self.conversation.get_recent_history()
        if not recent_history: # Không có gì để xử lý
             return None
        # add history
        self._create_prompt(recent_history, **kwargs)
        llm_response = self._llm_service.generate(self.prompt) 
        return llm_response

    def process_new_event(self, **kwargs):
        print(f"--- AGENT {self.agent_name}: Entered process_new_event")
        # Acquire the RLock (non-blocking)
        print(f"--- AGENT {self.agent_name}: Attempting to acquire agent RLock...")
        if not self._lock.acquire(blocking=False):
            print(f"--- AGENT {self.agent_name}: Already processing (RLock held). Skipping.")
            return
        print(f"--- AGENT {self.agent_name}: Acquired agent RLock.")

        try:
            # Status update is now safe because RLock is re-entrant
            self._update_status("thinking")
            

            llm_response = self._think(**kwargs) # Calls methods that might use Conversation lock

            actionable_response = self._decide_action(llm_response)
            

            if actionable_response:
                self._update_status("typing") # Safe call
                
                # --- Tách tin nhắn nếu cần ---
                messages = actionable_response.split(" ||| ")
                
                for idx, msg in enumerate(messages):
                    msg = msg.strip()
                    if not msg:
                        continue

                    # 1) Thời gian “suy nghĩ” ngắn giữa các message
                    think_time = random.uniform(1, 2)
                    time.sleep(think_time)

                    # 2) Tính delay typing dựa trên độ dài mỗi msg
                    text_length = len(msg)
                    per_char_time = random.uniform(0.02, 0.06)  # tốc độ nhanh hơn: 20–60ms/char
                    typing_time = text_length * per_char_time
                    typing_time = min(typing_time, 8)  # giới hạn max 8s
                    time.sleep(typing_time)

                    # 3) Gửi và broadcast riêng từng msg
                    if self.get_status() == "typing":
                        ai_message = self.conversation.add_message(self.agent_name, msg)
                        self.event_manager.broadcast_new_message(ai_message)
                    else:
                        break  # nếu status đổi, ngừng gửi

                self._update_status("idle") # Safe call
            else:
                self._update_status("idle") # Safe call

        except Exception as e:
            print(f"!!! ERROR in process_new_event for agent {self.agent_name}: {e}")
            # Ensure status is reset even on error
            try:
                # Check current status before forcing idle, maybe it was already set
                current_locked_status = self.get_status() # Safe call with RLock
                if current_locked_status != "idle":
                     print(f"--- AGENT {self.agent_name}: Setting status to idle due to error.")
                     self._update_status("idle") # Safe call
            except Exception as e_inner:
                print(f"!!! ERROR updating status to idle after error for {self.agent_name}: {e_inner}")
        finally:
            print(f"--- AGENT {self.agent_name}: Releasing agent RLock...")
            self._lock.release()
            print(f"--- AGENT {self.agent_name}: Released agent RLock.")

    def cleanup(self):
         """Unsubscribe the agent from the event manager."""
         if self.event_manager:
              print(f"--- AGENT {self.agent_name}: Cleaning up and unsubscribing.")
              self.event_manager.unsubscribe_agent(self.agent_name)
              
    def __del__(self):
        # Gọi cleanup khi đối tượng bị hủy (không đảm bảo luôn được gọi trong mọi TH)
        self.cleanup()
        
    def _human_like_typing(text):
        pointer = 0
        length = len(text)
        while pointer < length:
            # Random số ký tự sẽ "gõ" lần này (5 đến 15 ký tự)
            chunk_size = random.randint(5, 15)
            end = min(pointer + chunk_size, length)
            chunk = text[pointer:end]
            print(chunk, end='', flush=True)  # Giả vờ in từng chunk ra nếu muốn

            # Nếu chunk kết thúc bằng dấu ngắt câu, nghỉ lâu hơn
            if chunk[-1] in ['.', '!', '?', ',']:
                pause = random.uniform(0.5, 1.0)  # Nghỉ lâu
            else:
                pause = random.uniform(0.05, 0.2)  # Nghỉ ngắn

            time.sleep(pause)
            pointer = end