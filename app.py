# app.py
from ast import literal_eval
import asyncio
import re
import time
import uuid
import json
import traceback
from flask import (
    Flask, render_template, Response, jsonify, redirect, request, url_for, flash
)
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from database import database
import os

from flow.utils.helpers import create_agent_config, load_yaml
from flow.scriptGenerationFlow import generate_script_and_roles
from flow.dialogueFlow import DialogueFlow

from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- Initialize Database ---
database.init_app(app)
with app.app_context():
    db_path = os.path.join(app.root_path, 'chat_sessions.db')
    if not os.path.exists(db_path):
        print("--- APP: Database not found, initializing...")
        from database.database import init_db
        init_db()
    else:
        print("--- APP: Database already exists.")
        
# --- Initialize Config Files ---
folder_path = "flow/crews/config"
original_agents_config_path = f"{folder_path}/agents.yaml"
base_participants_path = f"{folder_path}/base_participants.yaml"
meta_agents_path = f"{folder_path}/meta_agents.yaml"
dynamic_participants_path = f"{folder_path}/dynamic_participants.yaml"
output_path = f"{folder_path}/agents.yaml"
base_script_path = f"{folder_path}/base_script.yaml"
dynamic_script_path = f"{folder_path}/dynamic_script.yaml"
problem_path = f"{folder_path}/problems.yaml"

# --- Load Config Files ---
problem_list_data = load_yaml(problem_path)

dialogue_flow = None

# --- Agent/System Cleanup on Exit ---
# def cleanup_system():
#     print("--- APP: Cleaning up system before exit ---")
#     if 'agent_manager' in globals() and 'agent_manager': 'agent_manager'.cleanup()
#     if interaction_coordinator: interaction_coordinator.cleanup()
#     print("--- APP: Cleanup complete ---")
# atexit.register(cleanup_system)


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
        '''SELECT session_id, user_name, problem, 
                    script, roles, current_stage_id, 
                    conversation, log_file, stage_state, inner_thought
                    FROM sessions 
                    WHERE session_id = ?''', (session_id,)
    ).fetchone()

    if session_data is None:
        flash(f"Session ID '{session_id}' not found.", "error")
        return redirect(url_for('list_sessions'))

    # --- Initialize Core Components with latest config for THIS session ---

    problem_for_session = session_data['problem']
    roles = session_data['roles']
    
    if roles is None:
        participants = load_yaml(original_agents_config_path)
    else:
        participants = json.loads(roles)

    participant_list = []
    
    agent_list = [agent_name for agent_name, agent_description in participants.items()]
    
    for agent_name in agent_list:
        participant_list.append({
            'id': agent_name,
            'name': agent_name,
            'avatar_initial': agent_name[0].upper() if agent_name else 'A'
        })
        
    stage_state = json.loads(session_data['stage_state'])
    inner_thought = literal_eval(session_data['inner_thought'])
    script = json.loads(session_data['script'])

    kwargs = {
        "problem": problem_for_session,
        "current_stage_id": session_data['current_stage_id'],
        "script": script,
        "participants": agent_list,
        "conversation": session_data['conversation'],
        "filename": session_data['log_file'],
        "inner_thought": inner_thought,
        "stage_state": stage_state
    }   
    
    # The code initializes a global variable `dialogue_flow` with an instance of the `DialogueFlow` class.
    # This is done to maintain the state of the conversation across multiple turns within the same session.
    # The `global` keyword is used to indicate that we are working with a variable defined outside the scope of this function.
    global dialogue_flow
    dialogue_flow = DialogueFlow(**kwargs)
    print(f"--- APP: Dialogue flow initialized for session {session_id}")
    
    return render_template('chat_interface.html',
                           participants=participant_list,
                           problem=problem_for_session,
                           session_id=session_id,
                           user_name=session_data['user_name'])

@app.route('/history/<session_id>')
def history(session_id):
    """Returns event history for a specific session."""
    db = database.get_db()
    session_exists = db.execute('SELECT 1 FROM sessions WHERE session_id = ?', (session_id,)).fetchone()
    if not session_exists:
        return jsonify({"error": "Session not found"}), 404

    session_history = db.execute(
        'SELECT conversation FROM sessions WHERE session_id = ?',
        (session_id,)
    ).fetchone()
    
    history_list = []
    if session_history and session_history[0]:
        lines = session_history[0].split('\n')
        for line in lines:
            pattern = r"TIME=([0-9.]+) \| CON#(\d+) \| SENDER=([^|]+) \| TEXT=(.+)"
            match = re.match(pattern, line)
            if match:
                try:
                    time_val, turn, sender, text = match.groups()
                    timestamp = float(time_val)
                    turn = int(turn)
                    sender_name = sender.strip()
                    text = text.strip()
                    history_list.append({
                        "source": sender_name,
                        "content": {
                            "text": text,
                            "sender_name": sender_name
                        },
                        "timestamp": timestamp * 1000  # Convert to milliseconds
                    })
                except (IndexError, ValueError) as e:
                    print(f"Error parsing line: {line} - {e}")
                    continue
    
    return jsonify(history_list)

# --- Socket.IO Events ---
@socketio.on('connect')
def handle_connect():
    print(f"--- SOCKETIO: Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    print(f"--- SOCKETIO: Client disconnected: {request.sid}")

@socketio.on('join')
def handle_join(data):
    """Client joins a specific session room"""
    session_id = data.get('session_id')
    if not session_id:
        emit('error', {'message': 'Session ID is required'})
        return
    
    # Check if session exists
    with app.app_context():
        db = database.get_db()
        if not db.execute('SELECT 1 FROM sessions WHERE session_id = ?', (session_id,)).fetchone():
            emit('error', {'message': 'Session not found'})
            return
    
    join_room(session_id)
    print(f"--- SOCKETIO [{session_id}]: Client {request.sid} joined room")
    emit('joined', {'status': 'success', 'session_id': session_id}, room=request.sid)

@socketio.on('leave')
def handle_leave(data):
    """Client leaves a specific session room"""
    session_id = data.get('session_id')
    if session_id:
        leave_room(session_id)
        print(f"--- SOCKETIO [{session_id}]: Client {request.sid} left room")

@socketio.on('user_message')
def handle_user_message(data):
    """Handle incoming user messages"""
    session_id = data.get('session_id')
    text = data.get('text', '').strip()
    sender_name = data.get('sender_name', 'User').strip()
    
    if not session_id or not text:
        emit('error', {'message': 'Session ID and message text are required'})
        return
    
    # Check if session exists
    with app.app_context():
        db = database.get_db()
        session_data = db.execute('SELECT user_name FROM sessions WHERE session_id = ?', (session_id,)).fetchone()
        if not session_data:
            emit('error', {'message': 'Session not found'})
            return
    
    sender_id = f"user-{sender_name.lower().replace(' ', '-')}"
    print(f"--- SOCKETIO [{session_id}]: Received message from '{sender_name}' ({sender_id}): {text}")
    emit('new_message', {
        'source': 'user',
        'content': {
            'text': text,
            'sender_name': sender_name
        },
        'timestamp': int(time.time() * 1000)
    }, room=session_id, namespace='/')

    # Confirm receipt to sender
    emit('message_received', {
        'status': 'success',
        'sender_used': sender_name
    }, room=request.sid)

    # --- DIALOGUE FLOW: Process new message ---
    global dialogue_flow
    if dialogue_flow:
        try:
            dialogue_flow.process_new_message(sender_name, text)
        except Exception as e:
            print(f"!!! ERROR in dialogue flow: {e}")
            traceback.print_exc()
            emit('error', {'message': f'Lỗi trong quá trình xử lý tin nhắn: {str(e)}'})
    else:
        print("!!! WARNING: dialogue_flow is not initialized.")
        emit('error', {'message': 'Lỗi: Phiên trò chuyện chưa được khởi tạo.'})

@socketio.on('agent_message')
def handle_agent_message(data):
    """Handle incoming agent messages"""
    session_id = data.get('session_id')
    text = data.get('text', '').strip()
    sender_name = data.get('sender_name', 'Agent').strip()

    if not session_id or not text:
        emit('error', {'message': 'Session ID and message text are required'})
        return

    # Check if session exists
    with app.app_context():
        db = database.get_db()
        session_data = db.execute('SELECT user_name FROM sessions WHERE session_id = ?', (session_id,)).fetchone()
        if not session_data:
            emit('error', {'message': 'Session not found'})
            return

    sender_id = f"agent-{sender_name.lower().replace(' ', '-')}"
    print(f"--- SOCKETIO [{session_id}]: Received message from '{sender_name}' ({sender_id}): {text}")
    emit('new_message', {
        'source': 'agent',
        'content': {
            'text': text,
            'sender_name': sender_name
        },
        'timestamp': int(time.time() * 1000)
    }, room=session_id, namespace='/')

    # --- DIALOGUE FLOW: Process new message ---
    global dialogue_flow
    if dialogue_flow:
        try:
            dialogue_flow.process_new_message(sender_name, text)
        except Exception as e:
            print(f"!!! ERROR in dialogue flow: {e}")
            traceback.print_exc()
            emit('error', {'message': f'Lỗi trong quá trình xử lý tin nhắn: {str(e)}'})
    else:
        print("!!! WARNING: dialogue_flow is not initialized.")
        emit('error', {'message': 'Lỗi: Phiên trò chuyện chưa được khởi tạo.'})

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

    try:
        kwargs = {
            "problem": problem_text,
            "solution": solution_text,
            "keywords": keywords_list
        }
        script, roles = generate_script_and_roles(folder_path, **kwargs)
    except Exception as e:
        print(f"!!! ERROR generating or saving script/personas: {e}")
        traceback.print_exc()
        flash("Có lỗi xảy ra trong quá trình tạo kịch bản. Sử dụng kịch bản mặc định (nếu có).", "warning")

    # Create agent config from dynamic script and roles for this session
    create_agent_config(
        dynamic_participants_path,
        meta_agents_path,
        output_path
    )

    # Create new session in DB
    session_id = str(uuid.uuid4())
    db = database.get_db()

    try:
        current_stage_id = "1"
        log_file = f"logs/{session_id}.log"
        stage_state = {
            "completed_task_ids": [],
            "signal": "1"
        }
        conversation = f"TIME={time.time()} | CON#0 | SENDER=System | TEXT=Chào mừng các bạn đến với lớp học. Bài toán của chúng ta là: {problem_text}"
        inner_thought = "[]" # Initialize as an empty list string
        db.execute(
            '''INSERT INTO sessions (session_id, user_name, 
                                    problem, script, roles, 
                                    current_stage_id, conversation, 
                                    log_file, stage_state, inner_thought) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                    (session_id, username, 
                                    problem_text, script, roles, 
                                    current_stage_id, conversation, 
                                    log_file, json.dumps(stage_state), inner_thought)
        )
        db.commit()
        print(f"--- APP: Created new session {session_id} for user {username} (problem {problem_id}) ---")
        
        return redirect(url_for('chat_interface', session_id=session_id))
    
    except Exception as e:
        print(f"!!! ERROR creating new session in DB: {e}")
        traceback.print_exc()
        db.rollback()
        flash("Có lỗi xảy ra khi tạo phiên trò chuyện mới.", "error")
        return redirect(url_for('select_problem_page'))

if __name__ == '__main__':
    socketio.run(app, debug=True, use_reloader=False)

