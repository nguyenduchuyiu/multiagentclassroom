# agent.py
import json
import random
import time
import threading # Import threading
from services.llm_service import LLMService


class BaseAgent:
    def __init__(self, agent_id: str, event_manager, conversation, role_description: str, **config):
        self.agent_id = agent_id
        self.event_manager = event_manager
        self.conversation = conversation
        self.role_description = role_description
        self._llm_service = LLMService(model_name="gemini-2.0-flash", **config) # Use the correct model name
        self._lock = threading.RLock() # Use Reentrant Lock
        self._current_status = "idle"
        # --- Đăng ký agent với EventManager ---
        if self.event_manager:
            self.event_manager.subscribe_agent(self)

    def _update_status(self, status):
        # Now this is safe even if called from process_new_event
        with self._lock:
            # Check if status actually changed to avoid redundant updates/broadcasts
            if self._current_status == status:
                # print(f"--- AGENT STATUS: {self.agent_id} already '{status}'. Skipping update.")
                return # No change, do nothing
            self._current_status = status
            print(f"AGENT STATUS: {self.agent_id} is now {status}") # Log the change

        # Broadcast outside the lock to avoid holding agent lock while potentially
        # waiting for event manager lock (reduces potential deadlock scenarios further, though unlikely here)
        self.event_manager.broadcast_agent_status(self.agent_id, status)


    def get_status(self):
         with self._lock: # RLock is safe here too
              return self._current_status

    def _create_prompt(self, recent_history):
        """Tạo prompt cụ thể cho LLM. Sẽ được override bởi lớp con."""
        history_text = "\n".join([f"{msg['sender']}: {msg['text']}" for msg in recent_history])
        last_message = recent_history[-1] if recent_history else None

        prompt = f"{self.role_description}\n"
        prompt += "--- Lịch sử chat gần đây ---\n"
        prompt += f"{history_text}\n"
        prompt += "--- Kết thúc lịch sử ---\n"
        if last_message:
            prompt += f"Tin nhắn mới nhất từ {last_message['sender']} là: {last_message['text']}\n"
        return prompt

    def _decide_action(self, llm_response):
        """Quyết định có phản hồi hay không dựa trên kết quả LLM."""
        # Logic đơn giản: nếu không phải NO_RESPONSE và không rỗng thì trả lời
        print("raw ", llm_response)
        llm_response = json.loads(llm_response)
        if llm_response:
            if llm_response["text"].strip().upper() != "NO_RESPONSE":
                return llm_response["text"].strip()
        return None

    def _think(self):
        """Quá trình suy nghĩ: lấy history, tạo prompt, gọi LLM."""
        recent_history = self.conversation.get_recent_history()
        if not recent_history: # Không có gì để xử lý
             return None

        prompt = self._create_prompt(recent_history)
        llm_response = self._llm_service.generate(prompt) # Gọi dịch vụ LLM
        return llm_response

    def process_new_event(self):
        print(f"--- AGENT {self.agent_id}: Entered process_new_event")
        # Acquire the RLock (non-blocking)
        print(f"--- AGENT {self.agent_id}: Attempting to acquire agent RLock...")
        if not self._lock.acquire(blocking=False):
            print(f"--- AGENT {self.agent_id}: Already processing (RLock held). Skipping.")
            return
        print(f"--- AGENT {self.agent_id}: Acquired agent RLock.")

        try:
            # Status update is now safe because RLock is re-entrant
            self._update_status("thinking")

            llm_response = self._think() # Calls methods that might use Conversation lock

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
                        ai_message = self.conversation.add_message(self.agent_id, msg)
                        self.event_manager.broadcast_new_message(ai_message)
                    else:
                        break  # nếu status đổi, ngừng gửi

                self._update_status("idle") # Safe call
            else:
                self._update_status("idle") # Safe call

        except Exception as e:
            print(f"!!! ERROR in process_new_event for agent {self.agent_id}: {e}")
            # Ensure status is reset even on error
            try:
                # Check current status before forcing idle, maybe it was already set
                current_locked_status = self.get_status() # Safe call with RLock
                if current_locked_status != "idle":
                     print(f"--- AGENT {self.agent_id}: Setting status to idle due to error.")
                     self._update_status("idle") # Safe call
            except Exception as e_inner:
                print(f"!!! ERROR updating status to idle after error for {self.agent_id}: {e_inner}")
        finally:
            print(f"--- AGENT {self.agent_id}: Releasing agent RLock...")
            self._lock.release()
            print(f"--- AGENT {self.agent_id}: Released agent RLock.")

    def cleanup(self):
         """Unsubscribe the agent from the event manager."""
         if self.event_manager:
              print(f"--- AGENT {self.agent_id}: Cleaning up and unsubscribing.")
              self.event_manager.unsubscribe_agent(self.agent_id)
              
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

# --- Lớp Agent cụ thể ---
class Khanh(BaseAgent):
    def __init__(self, agent_id, event_manager, conversation):
        role = "Bạn là Khánh - một sinh viên nam 20 tuổi học UET. Là bạn của Nam và Huy. Bạn là một chúa hề và mới nhận việc intern remote không lương ở một công ty startup bên Singapore. Hay nói bậy một chút."
        # Hướng dẫn cụ thể hơn cho Coder
        system_instruction = "Hãy tham gia trò chuyện sôi nổi với các bạn. Nếu người khác được hỏi đích danh, hãy im lặng và lắng nghe. Nếu không muốn trả lời hãy trả về {'text': 'NO_RESPONSE'}'. Chỉ trả về lời nói, không thêm gì hơn. Và nói ngắn thôi để phù hợp với việc chat qua lại."
        response_schema = {
                            "type": "object",
                            "properties": {
                                "text": {
                                "type": "string"
                                }
                            },
                            "required": [
                                "text"
                            ]
                        }
        super().__init__(agent_id=agent_id, 
                         event_manager=event_manager, 
                         conversation=conversation, 
                         role_description=role, 
                         system_instruction=system_instruction,
                         response_mime_type="application/json",
                         response_schema=response_schema)
    # Có thể override _create_prompt hoặc _decide_action nếu cần logic riêng

class Nam(BaseAgent):
     def __init__(self, agent_id, event_manager, conversation):
        role = "Bạn là Nam - một sinh viên nam 20 tuổi học UET. Là bạn của Khánh và Huy. Thích phông bạt, hay vẽ ra những viễn cảnh tương lai đẹp, vẽ ra những kế hoạch để giải quyết một công việc nào đó. Thích những thứ nghệ nghệ."
        system_instruction = (
            "Hãy tham gia trò chuyện sôi nổi với các bạn. "
            "Nếu người khác được hỏi đích danh, hãy im lặng và lắng nghe. "
            "Nếu không muốn trả lời, hãy trả về {'text': 'NO_RESPONSE'}. "
            "Chỉ trả về lời nói, không thêm gì hơn. "
            "Trả lời câu hỏi của người khác trực tiếp, không được vòng vo chờ đợi."
            "Bạn có thể chia các câu để follow up bằng dấu ' ||| ' (ba dấu gạch đứng và khoảng trắng) tránh việc tin nhắn quá dài, ví dụ: 'Ừ, nghe vui đấy! ||| Nhưng có chắc không vậy?' 'B1: Làm như này ||| B2: Làm như kia ...etc'"
            "Không bao giờ thêm bất cứ định dạng nào khác ngoài ' ||| '.")
        response_schema = {
                            "type": "object",
                            "properties": {
                                "text": {
                                "type": "string"
                                }
                            },
                            "required": [
                                "text"
                            ]
                        }
        super().__init__(agent_id=agent_id, 
                         event_manager=event_manager, 
                         conversation=conversation, 
                         role_description=role, 
                         system_instruction=system_instruction,
                         response_mime_type="application/json",
                         response_schema=response_schema)
    # Có thể override _create_prompt hoặc _decide_action