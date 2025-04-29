# app.py (Refactored - With Flexible User Handling)
from flask import Flask, render_template, request, Response, jsonify
from flask_cors import CORS
import uuid
import json
import queue
import atexit
import os
import traceback # Added for better error logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import New Core Components
from core.conversation_history import ConversationHistory
from core.interaction_coordinator import InteractionCoordinator
from core.response_orchestrator import ResponseOrchestrator
from core.agent_manager import AgentManager
from core.speaker_selector import SpeakerSelector
from core.behavior_executor import BehaviorExecutor
from core.conversation_phase_manager import ConversationPhaseManager
from services.llm_service import LLMService
from utils.loaders import load_problem_context

app = Flask(__name__)
CORS(app)

# --- Constants & Configuration ---
PERSONA_CONFIG_PATH = "config/personas.yaml"
PHASE_CONFIG_PATH = "config/phases.yaml"
PROBLEM_CONTEXT_PATH = "config/problem_context.yaml" 
# --- Load Problem Context ---
print("--- APP: Loading Problem Context ---")
problem_context_data = load_problem_context(PROBLEM_CONTEXT_PATH)
if not problem_context_data:
    print(f"!!! FATAL ERROR: Could not load problem context from {PROBLEM_CONTEXT_PATH}. Exiting.")
    exit(1) # Exit if problem context is essential and failed to load

PROBLEM_DESCRIPTION = problem_context_data['problem']
SOLUTION_DESCRIPTION = problem_context_data['solution'] # Solution is also loaded

# --- Initialize Core Components ---
print("--- APP: Initializing Core Components ---")
try:
    conversation_history = ConversationHistory()
    llm_service = LLMService(model="gemini-2.0-flash", temperature=0.5) # Adjust model as needed
    phase_manager = ConversationPhaseManager(PHASE_CONFIG_PATH, PROBLEM_DESCRIPTION, llm_service)
    agent_manager = AgentManager(PERSONA_CONFIG_PATH, PROBLEM_DESCRIPTION, llm_service)
    speaker_selector = SpeakerSelector(PROBLEM_DESCRIPTION, llm_service)
    interaction_coordinator = InteractionCoordinator(conversation_history)
    behavior_executor = BehaviorExecutor(interaction_coordinator, PROBLEM_DESCRIPTION, llm_service, agent_manager)
    response_orchestrator = ResponseOrchestrator(
        conversation_history=conversation_history,
        phase_manager=phase_manager,
        agent_manager=agent_manager,
        speaker_selector=speaker_selector,
        behavior_executor=behavior_executor,
        interaction_coordinator=interaction_coordinator,
        problem_description=PROBLEM_DESCRIPTION,
    )
    interaction_coordinator.set_orchestrator(response_orchestrator)
    print("--- APP: Core Components Initialized Successfully ---")
except Exception as e:
     print(f"!!! FATAL ERROR during app initialization: {e}")
     traceback.print_exc()
     exit(1)

# --- Agent/System Cleanup on Exit ---
def cleanup_system():
    print("--- APP: Cleaning up system before exit ---")
    if agent_manager: agent_manager.cleanup()
    if interaction_coordinator: interaction_coordinator.cleanup()
    print("--- APP: Cleanup complete ---")
atexit.register(cleanup_system)

# --- Flask Routes ---

@app.route('/')
def index():
    # Prepare participant list for the template (AI agents only)
    participant_list = []
    if agent_manager:
         for agent_id, agent_mind in agent_manager.agents.items():
             persona = agent_mind.persona
             participant_list.append({
                 'id': persona.agent_id,
                 'name': persona.name,
                 'avatar_initial': persona.name[0].upper() if persona.name else 'A'
             })
    # <<< Pass the problem description to the template >>>
    return render_template('index.html',
                           participants=participant_list,
                           problem_description=PROBLEM_DESCRIPTION)

@app.route('/history')
def history():
    return jsonify(conversation_history.get_history())

@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "Message text is required"}), 400

    user_message_text = data.get('text', '').strip()
    # <<< Get sender_name from payload, default to 'User' if not provided >>>
    sender_name = data.get('sender_name', 'User').strip()
    if not sender_name: sender_name = 'User' # Fallback

    # <<< Generate a simple user ID based on the name (adjust if needed) >>>
    sender_id = f"user-{sender_name.lower().replace(' ', '-')}"

    if not user_message_text:
         return jsonify({"error": "Message text cannot be empty"}), 400

    print(f"--- APP: Received message from '{sender_name}' ({sender_id}): {user_message_text}")

    # Trigger InteractionCoordinator with the dynamic user info
    interaction_coordinator.handle_external_trigger(
        event_type="new_message",
        source=sender_id, # Use the generated/dynamic ID
        content={"text": user_message_text, "sender_name": sender_name} # Pass the name
    )

    return jsonify({"status": "Message received and processing initiated", "sender_used": sender_name}), 200

@app.route('/stream')
def stream():
    # SSE stream endpoint (remains the same logic)
    client_id = str(uuid.uuid4())
    sse_queue = interaction_coordinator.add_sse_client(client_id)
    if sse_queue is None:
         return Response("Could not establish stream.", status=500)
    print(f"--- APP: SSE client connected: {client_id}")

    def event_generator():
        try:
            while True:
                event_data = None
                try:
                    event_data = sse_queue.get(timeout=1)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                if event_data is None: break

                if isinstance(event_data.get('data'), (dict, list)):
                    data_str = json.dumps(event_data['data'])
                else:
                    data_str = str(event_data.get('data', ''))

                sse_event_type = event_data.get('event', 'message')
                sse_message = f"event: {sse_event_type}\ndata: {data_str}\n\n"
                yield sse_message
        except GeneratorExit:
            print(f"--- APP: SSE client disconnected (GeneratorExit): {client_id}")
        except Exception as e:
             print(f"!!! ERROR in SSE generator for {client_id}: {e}")
             traceback.print_exc()
        finally:
            print(f"--- APP: Removing SSE client from InteractionCoordinator: {client_id}")
            interaction_coordinator.remove_sse_client(client_id)

    response = Response(event_generator(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Connection'] = 'keep-alive'
    return response

if __name__ == '__main__':
    # Add initial system message - now includes the loaded problem description
    if not conversation_history.get_history():
         initial_text = f"Chào mừng các bạn! Chúng ta hãy cùng giải bài toán sau:\n\n{PROBLEM_DESCRIPTION}\n\nBắt đầu với giai đoạn 1: Tìm hiểu đề bài nhé!"
         initial_content = {"text": initial_text, "sender_name": "System"}
         interaction_coordinator.handle_internal_trigger(
             event_type="system_message",
             source="System",
             content=initial_content
         )

    app.run(debug=True, threaded=True, use_reloader=False)