# agent.py
import random
import time
import threading # Import threading
from services.llm_service import LLMService


class BaseAgent:
    def __init__(self, agent_id: str, event_manager, conversation, role_description: str, instructions: str):
        self.agent_id = agent_id
        self.event_manager = event_manager
        self.conversation = conversation
        self.role_description = role_description
        self.instructions = instructions
        # Khởi tạo LLMService (đã có)
        # Specify the model directly here or pass it
        self._llm_service = LLMService("gemini-2.0-flash") # Use the correct model name
        # self._llm_service = LLMService() # Or initialize without model if handled inside

        # --- SOLUTION: Use RLock instead of Lock ---
        self._lock = threading.RLock() # Use Reentrant Lock
        # -------------------------------------------
        self._current_status = "idle"

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
        prompt += f"Hướng dẫn: {self.instructions}\n"
        prompt += "--- Lịch sử chat gần đây ---\n"
        prompt += f"{history_text}\n"
        prompt += "--- Kết thúc lịch sử ---\n"
        if last_message:
            prompt += f"Tin nhắn mới nhất từ {last_message['sender']} là: {last_message['text']}\n"
        prompt += "Dựa vào vai trò, hướng dẫn và lịch sử, bạn có nên trả lời không? Nếu có, nội dung trả lời là gì? Nếu không, chỉ trả lời 'NO_RESPONSE'."
        # TODO: Thêm logic kiểm tra hỏi đích danh, etc. vào đây hoặc instructions
        return prompt

    def _decide_action(self, llm_response):
        """Quyết định có phản hồi hay không dựa trên kết quả LLM."""
        # Logic đơn giản: nếu không phải NO_RESPONSE và không rỗng thì trả lời
        if llm_response and llm_response.strip().upper() != "NO_RESPONSE":
            return llm_response.strip()
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
                # Consider adding a small sleep *here* if you want typing delay
                time.sleep(random.uniform(1, 5))

                # Calls method that uses Conversation lock
                ai_message = self.conversation.add_message(self.agent_id, actionable_response)
                # Calls method that uses EventManager lock
                self.event_manager.broadcast_new_message(ai_message)

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


# --- Lớp Agent cụ thể ---
class Khanh(BaseAgent):
    def __init__(self, agent_id, event_manager, conversation):
        role = "Bạn là Khánh - một sinh viên nam 20 tuổi học UET. Là bạn của Nam và Huy. Bạn là một chúa hề và mới nhận việc intern remote không lương ở một công ty startup bên Singapore. Hay nói bậy một chút."
        # Hướng dẫn cụ thể hơn cho Coder
        instructions = "Hãy tham gia trò chuyện sôi nổi với các bạn. Nếu người khác được hỏi đích danh, hãy im lặng và lắng nghe. Nếu không muốn trả lời hãy trả về 'NO_RESPONSE'"
        super().__init__(agent_id, event_manager, conversation, role, instructions)

    # Có thể override _create_prompt hoặc _decide_action nếu cần logic riêng

class Nam(BaseAgent):
     def __init__(self, agent_id, event_manager, conversation):
        role = "Bạn là Nam - một sinh viên nam 20 tuổi học UET. Là bạn của Khánh và Huy. Thích phông bạt, hay vẽ ra những viễn cảnh tương lai đẹp, vẽ ra những kế hoạch để giải quyết một công việc nào đó. Thích những thứ nghệ nghệ."
        instructions = "Hãy tham gia trò chuyện sôi nổi với các bạn. Nếu người khác được hỏi đích danh, hãy im lặng và lắng nghe. Nếu không muốn trả lời hãy trả về 'NO_RESPONSE'"
        super().__init__(agent_id, event_manager, conversation, role, instructions)
    # Có thể override _create_prompt hoặc _decide_action