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
from services.llm_service import LLMService
from utils.loaders import load_problem_context
from core.script_generation import ScriptGeneration
import yaml
import os

app = Flask(__name__)
CORS(app)

# --- Initialize Database ---
database.init_app(app)

# --- Constants & Configuration ---
PERSONA_CONFIG_PATH = "config/personas.yaml"
PHASE_CONFIG_PATH = "config/phases.yaml"
PROBLEM_LIST_PATH = "config/problems.yaml"

# --- Load Problem List ---
print("--- APP: Loading Problem List ---")
problem_list_data = load_problem_context(PROBLEM_LIST_PATH)
if not problem_list_data:
    print(f"!!! FATAL ERROR: Could not load problem list from {PROBLEM_LIST_PATH}. Exiting.")
    exit(1)

# --- Initialize Core Components (Minimal at startup) ---
print("--- APP: Initializing Core Components ---")
try:
    conversation_history = ConversationHistory()
    llm_service = LLMService(model="gemini-2.0-flash", temperature=1)
    interaction_coordinator = InteractionCoordinator(conversation_history)
    print("--- APP: Core Components Initialized Successfully ---")
except Exception as e:
    print(f"!!! FATAL ERROR during app initialization: {e}")
    traceback.print_exc()
    exit(1)

# --- Agent/System Cleanup on Exit ---
def cleanup_system():
    print("--- APP: Cleaning up system before exit ---")
    if 'agent_manager' in globals() and 'agent_manager': 'agent_manager'.cleanup()
    if interaction_coordinator: interaction_coordinator.cleanup()
    print("--- APP: Cleanup complete ---")
atexit.register(cleanup_system)


# --- Flask Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/list_sessions')
def list_sessions():
    """Lists existing chat sessions. This is the main entry point."""
    db = database.get_db()
    sessions = db.execute(
        'SELECT session_id, user_name, created_at FROM sessions ORDER BY created_at DESC'
    ).fetchall()
    return render_template('list_sessions.html', sessions=sessions)

@app.route('/select_problem', methods=['GET'])
def select_problem_page():
    """Displays the page for users to select a problem and enter details."""
    return render_template('selection.html')

@app.route('/chat/<session_id>')
def chat_interface(session_id):
    """Displays the main chat interface for a specific session."""
    db = database.get_db()
    session_data = db.execute(
        'SELECT session_id, user_name, problem_description FROM sessions WHERE session_id = ?', (session_id,)
    ).fetchone()

    if session_data is None:
        flash(f"Session ID '{session_id}' not found.", "error")
        return redirect(url_for('list_sessions'))

    # --- Initialize Core Components with latest config for THIS session ---
    from core.conversation_phase_manager import ConversationPhaseManager
    from core.agent_manager import AgentManager
    from core.speaker_selector import SpeakerSelector
    from core.behavior_executor import BehaviorExecutor
    from core.response_orchestrator import ResponseOrchestrator

    problem_description_for_session = session_data['problem_description']

    # Ensure app_instance=app is passed if components need it
    phase_manager = ConversationPhaseManager(PHASE_CONFIG_PATH, problem_description_for_session, llm_service, app_instance=app)
    agent_manager = AgentManager(PERSONA_CONFIG_PATH, problem_description_for_session, llm_service, app_instance=app)
    speaker_selector = SpeakerSelector(problem_description_for_session, llm_service)
    behavior_executor = BehaviorExecutor(interaction_coordinator, problem_description_for_session, llm_service, agent_manager, app_instance=app)
    response_orchestrator = ResponseOrchestrator(
        conversation_history=conversation_history,
        phase_manager=phase_manager,
        agent_manager=agent_manager,
        speaker_selector=speaker_selector,
        behavior_executor=behavior_executor,
        interaction_coordinator=interaction_coordinator,
        problem_description=problem_description_for_session,
        app_instance=app
    )
    interaction_coordinator.set_orchestrator(response_orchestrator) # Orchestrator is now specific to this request/session context

    participant_list = []
    if agent_manager:
         for agent_id, agent_mind in agent_manager.agents.items():
             persona = agent_mind.persona
             participant_list.append({
                 'id': persona.agent_id,
                 'name': persona.name,
                 'avatar_initial': persona.name[0].upper() if persona.name else 'A'
             })

    return render_template('chat_interface.html', # Changed from 'index.html' to 'chat_interface.html'
                           participants=participant_list,
                           problem_description=problem_description_for_session,
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

@app.route('/api/problems')
def get_problems():
    """
    API trả về danh sách các bài toán cho frontend.
    Chỉ trả về id và mô tả bài toán, không trả về solution.
    """
    problems = [
        {"id": pid, "text": pdata["problem"]}
        for pid, pdata in problem_list_data.items()
        if "problem" in pdata
    ]
    return jsonify(problems)

import os

with app.app_context():
    db_path = os.path.join(app.root_path, 'chat_sessions.db')
    if not os.path.exists(db_path):
        print("--- APP: Database not found, initializing...")
        from database import init_db
        init_db()
    else:
        print("--- APP: Database already exists.")

@app.route('/generate_script_and_start_chat', methods=['POST'])
def generate_script_and_start_chat():
    """
    Receives problem selection, generates script/personas, creates a new chat session,
    and redirects to the chat interface.
    """
    problem_id = request.form.get('problem_id')
    username = request.form.get('username', 'User').strip()
    if not username: # Ensure username is not empty
        username = 'User'
    keywords = request.form.get('keywords', '').strip()

    if not problem_id or problem_id not in problem_list_data:
        flash("Vui lòng chọn một bài toán hợp lệ.", "error")
        return redirect(url_for('select_problem_page'))

    problem_data = problem_list_data[problem_id]
    problem_text = problem_data.get('problem', '')
    solution_text = problem_data.get('solution', '') # Assuming solution is available for script generation

    if not problem_text:
        flash("Không tìm thấy nội dung bài toán đã chọn.", "error")
        return redirect(url_for('select_problem_page'))

    keywords_list = [kw.strip() for kw in keywords.split(",") if kw.strip()]

    # Generate script/phases and personas
    # This part saves to global files (config/phases.yaml, config/personas.yaml)
    # This is a known behavior; for true multi-session isolation, these would need to be session-specific.
    if solution_text: # Only generate if solution is available
        script_generator = ScriptGeneration(
            problem_description=problem_text,
            solution=solution_text,
            keywords=keywords_list
        )
        try:
            phases_yaml_str = script_generator.generate_script()
            phases_yaml_str = phases_yaml_str.replace("```yaml", "").replace("```", "").strip()
            with open(PHASE_CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(phases_yaml_str)
            print(f"--- APP: Saved generated phases to {PHASE_CONFIG_PATH} ---")

            personas_yaml_str = script_generator.generate_roles(script_yaml_str=phases_yaml_str)
            personas_yaml_str = personas_yaml_str.replace("```yaml", "").replace("```", "").strip()
            with open(PERSONA_CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write(personas_yaml_str)
            print(f"--- APP: Saved generated personas to {PERSONA_CONFIG_PATH} ---")
        except Exception as e:
            print(f"!!! ERROR generating or saving script/personas: {e}")
            traceback.print_exc()
            flash("Có lỗi xảy ra trong quá trình tạo kịch bản. Sử dụng kịch bản mặc định (nếu có).", "warning")
    else:
        print(f"--- APP: No solution text for problem {problem_id}. Skipping script/persona generation. Default files will be used. ---")
        # Optionally, ensure default/empty files exist or handle this case in component initialization

    # Create new session in DB
    session_id = str(uuid.uuid4())
    db = database.get_db()
    initial_metadata = {
        "status": "active",
        "current_phase_id": "1",
        "completed_tasks": {}
    }

    try:
        db.execute(
            "INSERT INTO sessions (session_id, user_name, problem_description, current_phase_id, metadata) VALUES (?, ?, ?, ?, ?)",
            (session_id, username, problem_text, "1", json.dumps(initial_metadata))
        )
        db.commit()
        print(f"--- APP: Created new session {session_id} for user {username} (problem {problem_id}) ---")

        initial_text = f"Chào mừng mọi người! Chúng ta hãy cùng giải bài toán:\n\n{problem_text}\n\nBắt đầu với giai đoạn 1: Tìm hiểu đề bài nhé!"
        initial_content = {"text": initial_text, "sender_name": "System"}
        conversation_history.add_event(
            session_id=session_id,
            event_type="system_message",
            source="System",
            content=initial_content
        )
        return redirect(url_for('chat_interface', session_id=session_id))
    except database.sqlite3.IntegrityError:
        flash("Lỗi tạo session (ID có thể đã tồn tại). Vui lòng thử lại.", "error")
        return redirect(url_for('select_problem_page'))
    except Exception as e:
        print(f"!!! ERROR creating new session in DB: {e}")
        traceback.print_exc()
        db.rollback()
        flash("Có lỗi xảy ra khi tạo phiên trò chuyện mới.", "error")
        return redirect(url_for('select_problem_page'))

if __name__ == '__main__':
    app.run(debug=True, threaded=True, use_reloader=False)