# event_manager.py
import queue
import threading
import json
# Import Agent base class để type hint và tránh circular import
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.agent import BaseAgent

class EventManager:
    def __init__(self):
        self._sse_queues = {} # { client_id: queue.Queue() }
        self._agent_subscribers = {} # { agent_id: agent_instance } -> Lưu trữ agent đăng ký
        self._lock = threading.Lock() # Lock chung cho cả queue và subscribers

    def subscribe_agent(self, agent: 'BaseAgent'):
        """Đăng ký một agent để nhận thông báo về sự kiện mới."""
        with self._lock:
            if agent.agent_id not in self._agent_subscribers:
                print(f"--- EVT_MGR: Subscribing agent {agent.agent_id}")
                self._agent_subscribers[agent.agent_id] = agent
            else:
                # Có thể cập nhật hoặc bỏ qua nếu đã tồn tại
                 print(f"--- EVT_MGR: Agent {agent.agent_id} already subscribed.")
                 pass # Hoặc cập nhật self._agent_subscribers[agent.agent_id] = agent

    def unsubscribe_agent(self, agent_id: str):
        """Hủy đăng ký agent."""
        with self._lock:
            if agent_id in self._agent_subscribers:
                print(f"--- EVT_MGR: Unsubscribing agent {agent_id}")
                del self._agent_subscribers[agent_id]

    def add_sse_client(self, client_id):
        q = queue.Queue()
        with self._lock:
            self._sse_queues[client_id] = q
            print(f"--- EVT_MGR: SSE client added: {client_id}") # Log thêm client
        return q

    def remove_sse_client(self, client_id):
         with self._lock:
             if client_id in self._sse_queues:
                 try: # Đảm bảo không lỗi nếu queue đã bị xử lý
                      self._sse_queues[client_id].put_nowait(None) # Gửi tín hiệu dừng
                 except queue.Full:
                      pass # Bỏ qua nếu full, client sắp bị xóa rồi
                 except Exception as e:
                      print(f"--- EVT_MGR WARN: Error putting None to queue for {client_id}: {e}")
                 del self._sse_queues[client_id]
                 print(f"--- EVT_MGR: SSE client removed: {client_id}") # Log xóa client

    def _trigger_agents(self, triggering_agent_id: str | None = None):
        """Kích hoạt các agent đã đăng ký (trừ agent gây ra trigger nếu có)."""
        agents_to_trigger = []
        with self._lock:
            # Tạo list agent cần trigger bên trong lock để tránh thay đổi dict khi đang duyệt
            for agent_id, agent in self._agent_subscribers.items():
                if agent_id != triggering_agent_id: # Không trigger chính agent vừa gửi tin
                    agents_to_trigger.append(agent)
                # else: # DEBUG
                #     print(f"--- EVT_MGR: Skipping trigger for sender agent {triggering_agent_id}")


        if agents_to_trigger:
             print(f"--- EVT_MGR: Triggering agents: {[a.agent_id for a in agents_to_trigger]}") # Log agent được trigger
             for agent in agents_to_trigger:
                 # Chạy process_new_event trong thread riêng để không block EventManager
                 thread = threading.Thread(target=agent.process_new_event, daemon=True)
                 # thread.daemon = True # Đảm bảo thread con tự thoát khi main thread thoát
                 thread.start()
        # else: # DEBUG
            # print(f"--- EVT_MGR: No other agents to trigger.")

    def broadcast_event(self, event_type, data, originating_agent_id: str | None = None):
        """Broadcasts sự kiện tới client và trigger các agent khác nếu là tin nhắn mới."""
        print(f"--- EVT_MGR: Broadcasting event: Type={event_type}, Origin={originating_agent_id or 'Human/System'}")
        event_payload = {"event": event_type, "data": data}

        # 1. Gửi sự kiện tới các SSE clients (trình duyệt)
        client_ids_to_broadcast = []
        with self._lock:
            # Lấy danh sách client ID trong lock
            client_ids_to_broadcast = list(self._sse_queues.keys())

        if not client_ids_to_broadcast:
            print("--- EVT_MGR: No active SSE clients to broadcast to.")
        else:
            # print(f"--- EVT_MGR: Broadcasting SSE to clients: {client_ids_to_broadcast}") # Log nhiều quá có thể bỏ
            for client_id in client_ids_to_broadcast:
                q = None
                with self._lock: # Lock lại để lấy queue an toàn
                    if client_id in self._sse_queues:
                        q = self._sse_queues[client_id]
                if q:
                    try:
                        # print(f"--- EVT_MGR: Attempting to put event to queue for client: {client_id}")
                        q.put_nowait(event_payload)
                        # print(f"--- EVT_MGR: Put successful for {client_id}")
                    except queue.Full:
                        print(f"!!! WARNING [EventManager]: SSE queue full for client {client_id}. Event lost.")
                    except Exception as e:
                        print(f"!!! ERROR [EventManager]: Error putting event to queue for {client_id}: {e}")
                # else: # Bị xóa giữa chừng
                    # print(f"--- EVT_MGR WARN: Queue not found for client {client_id} during broadcast (likely disconnected).")

        # 2. Trigger các agent khác nếu đây là tin nhắn mới
        if event_type == "new_message":
            # originating_agent_id là ID của agent gửi tin, hoặc None nếu từ Human/System
            self._trigger_agents(triggering_agent_id=originating_agent_id)


    def broadcast_new_message(self, message_dict):
        # Xác định người gửi là agent hay không
        sender_id = message_dict.get("sender")
        is_agent_message = sender_id in self._agent_subscribers # Kiểm tra xem sender có phải agent đã đăng ký không
        originating_agent_id = sender_id if is_agent_message else None
        self.broadcast_event("new_message", message_dict, originating_agent_id=originating_agent_id)

    def broadcast_agent_status(self, agent_id, status):
        status_data = {"agent_id": agent_id, "status": status}
        # Trạng thái agent không cần trigger agent khác
        self.broadcast_event("agent_status", status_data, originating_agent_id=None)