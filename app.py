# app.py
import uuid
import json
import queue
import atexit
import traceback
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, Response, jsonify, redirect, url_for, g, flash
)
from flask_cors import CORS

# Load environment variables
load_dotenv()

from database import database

# Import New Core Components
from core.conversation_history import ConversationHistory
from core.interaction_coordinator import InteractionCoordinator
from core.response_orchestrator import ResponseOrchestrator
from core.agent_manager import AgentManager
from core.speaker_selector import SpeakerSelector
from core.behavior_executor import BehaviorExecutor
from core.conversation_phase_manager import ConversationPhaseManager
from services.llm_service import LLMService
from utils.loaders import load_phases_from_yaml, load_problem_context

app = Flask(__name__)
CORS(app)

# --- Initialize Database ---
database.init_app(app)

# --- Constants & Configuration ---
PERSONA_CONFIG_PATH = "config/personas.yaml"
PHASE_CONFIG_PATH = "config/phases.yaml"
PROBLEM_CONTEXT_PATH = "config/problem_context.yaml"

# --- Load Problem Context ---
print("--- APP: Loading Problem Context ---")
problem_context_data = load_problem_context(PROBLEM_CONTEXT_PATH)
if not problem_context_data:
    print(f"!!! FATAL ERROR: Could not load problem context from {PROBLEM_CONTEXT_PATH}. Exiting.")
    exit(1)
PROBLEM_DESCRIPTION = problem_context_data['problem']
SOLUTION_DESCRIPTION = problem_context_data['solution']

# --- Initialize Core Components
print("--- APP: Initializing Core Components ---")
try:
    conversation_history = ConversationHistory()
    llm_service = LLMService(model="gemini-2.0-flash", temperature=1)
    phase_manager = ConversationPhaseManager(PHASE_CONFIG_PATH, PROBLEM_DESCRIPTION, llm_service, app_instance=app)
    agent_manager = AgentManager(PERSONA_CONFIG_PATH, PROBLEM_DESCRIPTION, llm_service, app_instance=app)
    speaker_selector = SpeakerSelector(PROBLEM_DESCRIPTION, llm_service)
    interaction_coordinator = InteractionCoordinator(conversation_history)
    behavior_executor = BehaviorExecutor(interaction_coordinator, PROBLEM_DESCRIPTION, llm_service, agent_manager, app_instance=app)
    response_orchestrator = ResponseOrchestrator(
        conversation_history=conversation_history,
        phase_manager=phase_manager,
        agent_manager=agent_manager,
        speaker_selector=speaker_selector,
        behavior_executor=behavior_executor,
        interaction_coordinator=interaction_coordinator,
        problem_description=PROBLEM_DESCRIPTION,
        app_instance=app
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
def list_sessions():
    """Lists existing chat sessions."""
    # DB access happens within request context here, no extra context needed
    db = database.get_db()
    sessions = db.execute(
        'SELECT session_id, user_name, created_at FROM sessions ORDER BY created_at DESC'
    ).fetchall()
    return render_template('list_sessions.html', sessions=sessions)

@app.route('/chat/new', methods=['POST'])
def new_chat():
    """Creates a new chat session."""
    # DB access happens within request context here
    user_name = request.form.get('username', 'User').strip()
    if not user_name:
        user_name = 'User'

    session_id = str(uuid.uuid4())
    db = database.get_db()
    
    initial_metadata = {
        "status": "active",
        "current_phase_id": "1", # Start at phase 1
        "completed_tasks": {} # Store completed tasks per phase: {"phase_id": ["task_id1", "task_id2"]}
    }

    try:
        db.execute(
            "INSERT INTO sessions (session_id, user_name, problem_description, current_phase_id, metadata) VALUES (?, ?, ?, ?, ?)",
            (session_id, user_name, PROBLEM_DESCRIPTION, "1", json.dumps(initial_metadata)) # Use json.dumps for metadata adapter
        )
        db.commit()
        print(f"--- APP: Created new session {session_id} for user {user_name} ---")

        # Add initial system message
        initial_text = f"Chào mừng các bạn! Chúng ta hãy cùng giải bài toán sau:\n\n{PROBLEM_DESCRIPTION}\n\nBắt đầu với giai đoạn 1: Tìm hiểu đề bài nhé!"
        initial_content = {"text": initial_text, "sender_name": "System"}
        # ConversationHistory needs app context if called outside request/app context scope,
        # but here it's still within the request context, so it should work.
        conversation_history.add_event(
             session_id=session_id,
             event_type="system_message",
             source="System",
             content=initial_content
         )

        return redirect(url_for('chat_interface', session_id=session_id))

    except database.sqlite3.IntegrityError: # More specific error
        flash("Error creating session ID (possible duplicate). Please try again.", "error")
        return redirect(url_for('list_sessions'))
    except Exception as e:
        print(f"!!! ERROR creating new session: {e}")
        traceback.print_exc()
        db.rollback()
        flash("An unexpected error occurred while creating the session.", "error")
        return redirect(url_for('list_sessions'))


@app.route('/chat/<session_id>')
def chat_interface(session_id):
    """Displays the main chat interface for a specific session."""
    # DB access within request context
    db = database.get_db()
    session_data = db.execute(
        'SELECT session_id, user_name FROM sessions WHERE session_id = ?', (session_id,)
    ).fetchone()

    if session_data is None:
        flash(f"Session ID '{session_id}' not found.", "error")
        return redirect(url_for('list_sessions'))

    participant_list = []
    if agent_manager:
         for agent_id, agent_mind in agent_manager.agents.items():
             persona = agent_mind.persona
             participant_list.append({
                 'id': persona.agent_id,
                 'name': persona.name,
                 'avatar_initial': persona.name[0].upper() if persona.name else 'A'
             })

    return render_template('index.html',
                           participants=participant_list,
                           problem_description=PROBLEM_DESCRIPTION,
                           session_id=session_id,
                           user_name=session_data['user_name'])


@app.route('/history/<session_id>')
def history(session_id):
    """Returns event history for a specific session."""
    # DB access within request context
    db = database.get_db()
    session_exists = db.execute('SELECT 1 FROM sessions WHERE session_id = ?', (session_id,)).fetchone()
    if not session_exists:
        return jsonify({"error": "Session not found"}), 404

    session_history = conversation_history.get_history(session_id=session_id)
    return jsonify(session_history)


@app.route('/send_message/<session_id>', methods=['POST'])
def send_message(session_id):
    """Handles sending a message within a specific session."""
    # DB access within request context
    db = database.get_db()
    session_data = db.execute('SELECT user_name FROM sessions WHERE session_id = ?', (session_id,)).fetchone()
    if not session_data:
        return jsonify({"error": "Session not found"}), 404

    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "Message text is required"}), 400

    user_message_text = data.get('text', '').strip()
    sender_name = data.get('sender_name', session_data['user_name']).strip()
    if not sender_name: sender_name = session_data['user_name']

    sender_id = f"user-{sender_name.lower().replace(' ', '-')}"

    if not user_message_text:
         return jsonify({"error": "Message text cannot be empty"}), 400

    print(f"--- APP [{session_id}]: Received message from '{sender_name}' ({sender_id}): {user_message_text}")

    # Trigger IC - This call happens within request context.
    # The IC then starts background threads which NEED their own context push.
    interaction_coordinator.handle_external_trigger(
        session_id=session_id,
        event_type="new_message",
        source=sender_id,
        content={"text": user_message_text, "sender_name": sender_name}
    )

    return jsonify({"status": "Message received and processing initiated", "sender_used": sender_name}), 200


@app.route('/stream/<session_id>')
def stream(session_id):
    """SSE stream endpoint for a specific session."""
    # <<< Add app context for initial DB check >>>
    with app.app_context():
        db = database.get_db()
        if not db.execute('SELECT 1 FROM sessions WHERE session_id = ?', (session_id,)).fetchone():
            error_data = json.dumps({'error': 'Session not found'})
            # Return immediately with error response
            return Response(f"event: error\ndata: {error_data}\n\n", mimetype='text/event-stream', status=404)

    # Continue if session exists
    client_id = str(uuid.uuid4())
    sse_queue = interaction_coordinator.add_sse_client(session_id, client_id)
    if sse_queue is None:
         error_data = json.dumps({'error': 'Could not establish stream queue'})
         return Response(f"event: error\ndata: {error_data}\n\n", mimetype='text/event-stream', status=500)

    print(f"--- APP [{session_id}]: SSE client connected: {client_id}")

    def event_generator():
        # <<< Add app context for robustness during cleanup (optional but recommended) >>>
        with app.app_context():
            try:
                while True:
                    event_data = None
                    try:
                        # Use a slightly longer timeout to reduce keep-alive frequency if needed
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
                print(f"--- APP [{session_id}]: SSE client disconnected (GeneratorExit): {client_id}")
            except Exception as e:
                 print(f"!!! ERROR in SSE generator for {session_id}/{client_id}: {e}")
                 traceback.print_exc()
            finally:
                # This runs within the app context pushed above
                print(f"--- APP [{session_id}]: Removing SSE client from InteractionCoordinator: {client_id}")
                interaction_coordinator.remove_sse_client(session_id, client_id)

    response = Response(event_generator(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Connection'] = 'keep-alive'
    return response

import os

with app.app_context():
    db_path = os.path.join(app.root_path, 'chat_sessions.db')
    if not os.path.exists(db_path):
        print("--- APP: Database not found, initializing...")
        from database import init_db
        init_db()
    else:
        print("--- APP: Database already exists.")


if __name__ == '__main__':
    app.run(debug=True, threaded=True, use_reloader=False)