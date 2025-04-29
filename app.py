# app.py
from flask import Flask, render_template, request, Response, jsonify
from flask_cors import CORS
import uuid
import json
import queue
import atexit

# Import core components
from core.conversation import Conversation
from core.event_manager import EventManager
from utils.agent_loader import AgentLoader

app = Flask(__name__)
CORS(app)

# Core components initialization
conversation = Conversation()
event_manager = EventManager()

# Agent Initialization
agent_loader = AgentLoader("config/agents.yaml", "config/tasks.yaml", event_manager, conversation)
agents = agent_loader.get_agents()

# Agent cleanup on exit
def cleanup_agents():
    print("--- APP: Cleaning up agents before exit ---")
    for agent in agents.values():
        if hasattr(agent, 'cleanup'): # Check if cleanup method exists
             agent.cleanup()
atexit.register(cleanup_agents)


# --- Routes ---

@app.route('/')
def index():
    # Prepare participant list for the template
    # Agents are added based on the loader
    participant_list = []
    for agent_name, agent in agents.items():
        participant_list.append({
            'id': agent.agent_id,
            'name': agent.agent_name,
            'avatar_initial': agent.agent_name[0].upper() if agent.agent_name else 'A'
        })
    # Note: The 'Human'/'Bạn' participant is hardcoded in the HTML template
    return render_template('index.html', participants=participant_list)

@app.route('/history')
def history():
    # Returns the list of message dictionaries
    return jsonify(conversation.get_history())

@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "Message text is required"}), 400

    user_message_text = data.get('text').strip()
    if not user_message_text:
         return jsonify({"error": "Message text cannot be empty"}), 400

    # <<< Get sender_name from payload, default to 'Human' if not provided >>>
    sender_name = data.get('sender_name', 'Human').strip()
    # Basic validation for sender name (optional)
    if not sender_name:
        sender_name = 'Human' # Fallback if empty string provided

    print(f"--- APP: Received message from '{sender_name}': {user_message_text}")

    # <<< Use the sender_name when adding the message >>>
    user_message = conversation.add_message(sender_name, user_message_text)

    # <<< Add sender_name to the broadcast payload for consistency (although JS primarily uses local name for user) >>>
    # This might be useful if multiple browser windows were connected as different users
    user_message['sender_name'] = sender_name

    # Broadcast the message (EventManager handles SSE)
    # originating_agent_id is None because this is not from an agent
    event_manager.broadcast_event("new_message", user_message, originating_agent_id=None)

    return jsonify({"status": "Message received", "sender_used": sender_name}), 200 # Echo back sender used

@app.route('/stream')
def stream():
    client_id = str(uuid.uuid4())
    sse_queue = event_manager.add_sse_client(client_id)
    if sse_queue is None:
         return Response("Could not establish stream.", status=500)
    print(f"SSE client connected: {client_id}")

    def event_generator():
        try:
            while True:
                event_data = None
                try:
                    # Use timeout to periodically check connection and send keep-alive
                    event_data = sse_queue.get(timeout=1) # 20 second timeout
                except queue.Empty:
                    # Send keep-alive comment to prevent timeout
                    yield ": keep-alive\n\n"
                    continue # Continue loop to wait for next event

                if event_data is None: # Signal to stop
                    print(f"--- APP: Stop signal received for SSE client {client_id}")
                    break

                # Prepare data string (ensure JSON for dict/list)
                if isinstance(event_data.get('data'), (dict, list)):
                    data_str = json.dumps(event_data['data'])
                else:
                    data_str = str(event_data.get('data', ''))

                # Format SSE message
                sse_event_type = event_data.get('event', 'message')
                sse_message = f"event: {sse_event_type}\ndata: {data_str}\n\n"
                # print(f"--- APP: Sending SSE to {client_id}: {sse_event_type}") # Debug log
                yield sse_message

        except GeneratorExit:
            # Client disconnected
            print(f"--- APP: SSE client disconnected (GeneratorExit): {client_id}")
        except Exception as e:
             print(f"!!! ERROR in SSE generator for {client_id}: {e}")
        finally:
            # Clean up the client queue
            print(f"--- APP: Removing SSE client: {client_id}")
            event_manager.remove_sse_client(client_id)

    # Create the Flask response for SSE
    response = Response(event_generator(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no' # Important for proxies like Nginx
    response.headers['Connection'] = 'keep-alive'
    return response

if __name__ == '__main__':
    # Add initial system message if history is empty
    if not conversation.get_history():
         # Use 'System' as the sender for system messages
         initial_message = conversation.add_message("System", "Chào mừng! Vui lòng nhập tên của bạn để bắt đầu.")
         # Add sender_name for consistency if needed by any client logic
         initial_message['sender_name'] = 'System'

    app.run(debug=True, threaded=True, use_reloader=False) # threaded=True is important