# app.py
from flask import Flask, render_template, request, Response, jsonify
from flask_cors import CORS
from sse_starlette.sse import EventSourceResponse
import threading
import uuid
import json
import queue


# Import các thành phần từ core và services
from core.conversation import Conversation
from core.event_manager import EventManager
from core.agent import Nam, Khanh # Hoặc một hàm tạo agent
# from config import AGENT_CONFIG # Nếu dùng file config

app = Flask(__name__)

CORS(app)

# Khởi tạo các thành phần quản lý lõi
conversation = Conversation()
event_manager = EventManager()

# --- Khởi tạo Agents (có thể đọc từ config) ---
# Ví dụ khởi tạo cứng
agents = {
    "Nam": Nam("Nam", event_manager, conversation),
    "Khánh": Khanh("Khánh", event_manager, conversation)
}
# Hoặc dùng một hàm/lớp để quản lý agent lifecycle

# --- API Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/history')
def history():
    return jsonify(conversation.get_history())

@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.get_json()
    user_message_text = data.get('text')
    if not user_message_text:
        return jsonify({"error": "Message text is required"}), 400

    # Lưu tin nhắn người dùng thông qua Conversation manager
    user_message = conversation.add_message("Human", user_message_text)

    # Phát sự kiện tin nhắn mới qua EventManager (sẽ tự động gửi SSE)
    event_manager.broadcast_new_message(user_message)

    # Kích hoạt các agent suy nghĩ (thông qua EventManager hoặc gọi trực tiếp)
    for agent in agents.values():
         # Chạy trong thread để không block request
        thread = threading.Thread(target=agent.process_new_event)
        thread.daemon = True
        thread.start()

    return jsonify({"status": "Message received"}), 200

@app.route('/stream')
def stream():
    client_id = str(uuid.uuid4())
    # Dùng get() để tránh lỗi nếu client ngắt kết nối ngay lập tức
    sse_queue = event_manager.add_sse_client(client_id)
    if sse_queue is None:
         # Xử lý trường hợp không thêm được client (ví dụ: lỗi lock)
         return Response("Could not establish stream.", status=500)
    print(f"SSE client connected: {client_id}")

    # --- Hàm event_generator() đã sửa ở trên ---

    def event_generator():
        try:
            while True:
                try:
                    event_data = sse_queue.get(timeout=1)  # 1s timeout
                except queue.Empty:
                    # every 15s with no events, send a comment so proxies don’t kill the connection
                    yield ": keep-alive\n\n"
                    continue

                if event_data is None:
                    break

                # Đảm bảo data là string JSON nếu nó là dict/list
                if isinstance(event_data.get('data'), (dict, list)):
                    data_str = json.dumps(event_data['data'])
                else:
                    data_str = str(event_data.get('data', '')) # Xử lý trường hợp khác

                # Format chuỗi theo chuẩn SSE
                sse_message = f"event: {event_data.get('event', 'message')}\ndata: {data_str}\n\n"
                yield sse_message # <<< Quan trọng: yield chuỗi đã định dạng

        except GeneratorExit:
            print(f"SSE client disconnected by generator exit: {client_id}")
        finally:
            event_manager.remove_sse_client(client_id)
            print(f"SSE client removed: {client_id}")

    # Trả về đối tượng flask.Response tiêu chuẩn
    # Truyền generator và đặt mimetype đúng
    response = Response(event_generator(), mimetype='text/event-stream')
    # Thêm các header cần thiết cho SSE để tránh caching và buffering proxy
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no' # Quan trọng khi dùng Nginx
    response.headers['Connection'] = 'keep-alive' # Giữ kết nối mở

    return response
        
if __name__ == '__main__':
    # Thêm tin nhắn chào mừng ban đầu qua Conversation manager
    if not conversation.get_history():
         conversation.add_message("System", "Chào mừng đến với ChatCollab Demo!")
    app.run(debug=True, threaded=True) # threaded=True quan trọng cho SSE và background tasks