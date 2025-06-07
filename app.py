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
import signal

from flow.utils.helpers import create_agent_config, load_yaml, save_yaml
from flow.scriptGenerationFlow import generate_script_and_roles
from flow.dialogueFlow import DialogueFlow

from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = "your-very-secret-key"
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
sid_to_session = {}  # Dictionary to map socket ID to session ID

# --- Agent/System Cleanup on Exit ---
# def cleanup_system():
#     print("--- APP: Cleaning up system before exit ---")
#     if 'agent_manager' in globals() and 'agent_manager': 'agent_manager'.cleanup()
#     if interaction_coordinator: interaction_coordinator.cleanup()
#     print("--- APP: Cleanup complete ---")
# atexit.register(cleanup_system)

def initialize_dialogue_flow(session_id):
    db = database.get_db()
    session_data = db.execute(
        '''SELECT session_id, user_name, problem, 
                    script, roles, current_stage_id, 
                    conversation, log_file, stage_state, inner_thought,
                    turn_number
                    FROM sessions 
                    WHERE session_id = ?''', (session_id,)
    ).fetchone()

    if session_data is None:
        print(f"!!! ERROR: Session ID '{session_id}' not found.")
        return None

    # --- Initialize Core Components with latest config for THIS session ---

    problem_for_session = session_data['problem']
    roles = session_data['roles']
    
    if roles is None:
        roles = load_yaml(base_participants_path)
    else:
        roles = json.loads(roles)

    save_yaml(dynamic_participants_path, roles)

    create_agent_config(
        dynamic_participants_path,
        meta_agents_path,
        output_path
    )

    participant_list = []
    
    agent_list = [agent_name for agent_name, agent_description in roles.items()]
    
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
        "stage_state": stage_state,
        "session_id": session_id,
        "user_name": session_data['user_name'],
        "turn_number": session_data['turn_number'],
        "roles": roles
    }   
    
    global dialogue_flow
    dialogue_flow = DialogueFlow(socketio=socketio, **kwargs)
    print(f"--- APP: Dialogue flow initialized for session {session_id}")
    return session_data

def create_session(session_data):
    """
    Create a new session in the database.
    """
    db = database.get_db()      
    db.execute(
        '''INSERT INTO sessions (
            session_id, user_name, problem, script, roles,
            current_stage_id, conversation, log_file, stage_state,
            inner_thought, turn_number
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (session_data['session_id'],
         session_data['user_name'],
         session_data['problem'],
         json.dumps(session_data['script']),
         json.dumps(session_data['roles']),
         session_data['current_stage_id'],
         session_data['conversation'],
         session_data['log_file'],
         json.dumps(session_data['stage_state']),
         json.dumps(list(session_data['inner_thought'])), # Ensure inner_thought is a list
         session_data['turn_number'])
    )
    db.commit()
    print(f"--- APP: Created session {session_data['session_id']} in DB.")


def save_session_data(session_data):
    """
    Save the session data to the database (update existing).
    """
    db = database.get_db()
    # Ensure inner_thought is a list before converting to JSON for saving
    inner_thought_list = list(session_data.get('inner_thought', []))

    db.execute(
        '''UPDATE sessions SET
            problem = ?,
            script = ?,
            roles = ?,
            current_stage_id = ?,
            conversation = ?,
            log_file = ?,
            stage_state = ?,
            inner_thought = ?,
            turn_number = ?,
            user_name = ?
            WHERE session_id = ?''',
        (session_data['problem'],
         json.dumps(session_data['script']),
         json.dumps(session_data['roles']),
         session_data['current_stage_id'],
         session_data['conversation'],
         session_data['log_file'],
         json.dumps(session_data['stage_state']),
         json.dumps(inner_thought_list),
         session_data['turn_number'],
         session_data['user_name'],
         session_data['session_id'])
    )
    db.commit()
    print(f"--- APP: Saved session data for session {session_data['session_id']}")
    # print(f'''--- APP: Saved session data for session {session_data['session_id']} 
    #       with turn number {session_data['turn_number']}
    #       and current stage {session_data['current_stage_id']}
    #       and conversation {session_data['conversation']}
    #       and log file {session_data['log_file']}
    #       and stage state {session_data['stage_state']}
    #       and inner thought {session_data['inner_thought']}
    #       and script {session_data['script']}
    #       and roles {session_data['roles']}
    #       and user name {session_data['user_name']}
    #       ''')


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
    session_data = initialize_dialogue_flow(session_id)
    if session_data is None:
        return redirect(url_for('list_sessions'))
    
    roles = session_data['roles']
    
    if roles is None:
        participants = load_yaml(base_participants_path)
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
        
    problem_for_session = session_data['problem']
    user_name = session_data['user_name']
    return render_template('chat_interface.html',
                           participants=participant_list,
                           problem=problem_for_session,
                           session_id=session_id,
                           user_name=user_name)

@app.route('/history/<session_id>')
def history(session_id):
    """Returns event history for a specific session."""
    db = database.get_db()
    session_exists = db.execute('SELECT 1 FROM sessions WHERE session_id = ?', (session_id,)).fetchone()
    if not session_exists:
        return jsonify({"error": "Session not found"}), 404

    session_data = db.execute(
        '''SELECT conversation, script, current_stage_id, stage_state 
            FROM sessions 
            WHERE session_id = ?''',
        (session_id,)
    ).fetchone()
    
    history_list = []
    if session_data and session_data[0]:
        lines = session_data[0].split('\n')
        current_message = None
        for line in lines:
            pattern = r"TIME=([0-9.]+) \| CON#(\d+) \| SENDER=([^|]+) \| TEXT=(.+)"
            match = re.match(pattern, line)
            if match:
                # Nếu có message trước đó, lưu lại
                if current_message:
                    history_list.append(current_message)
                time_val, turn, sender, text = match.groups()
                timestamp = float(time_val)
                turn = int(turn)
                sender_name = sender.strip()
                text = text.strip()
                current_message = {
                    "source": sender_name,
                    "content": {
                        "text": text,
                        "sender_name": sender_name
                    },
                    "timestamp": timestamp * 1000  # Convert to milliseconds
                }
            else:
                # Nếu không match, đây là dòng tiếp theo của TEXT
                if current_message:
                    # Nối thêm dòng này vào text, giữ nguyên xuống dòng
                    current_message["content"]["text"] += "\n" + line
        # Đừng quên lưu message cuối cùng
        if current_message:
            history_list.append(current_message)
    
    script_content = json.loads(session_data["script"])
    stage_state = json.loads(session_data["stage_state"])
    completed_task_ids = stage_state.get("completed_task_ids", [])
    current_stage_id = session_data["current_stage_id"]
    
    return jsonify({
        "history": history_list,
        "script": script_content,
        "completed_task_ids": completed_task_ids,
        "current_stage_id": current_stage_id
    })

@app.route('/delete_session/<session_id>', methods=['POST'])
def delete_session(session_id):
    """Delete a chat session from the database."""
    try:
        db = database.get_db()
        # Check if session exists
        session = db.execute('SELECT 1 FROM sessions WHERE session_id = ?', (session_id,)).fetchone()
        if not session:
            flash("Session not found.", "error")
            return redirect(url_for('list_sessions'))
        
        # Delete the session
        db.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
        db.commit()
        
        # Try to delete the log file if it exists
        try:
            log_file = f"logs/{session_id}.log"
            if os.path.exists(log_file):
                os.remove(log_file)
        except Exception as e:
            print(f"Warning: Could not delete log file: {e}")
        
        flash("Session deleted successfully.", "success")
    except Exception as e:
        print(f"Error deleting session: {e}")
        flash("An error occurred while deleting the session.", "error")
        db.rollback()
    
    return redirect(url_for('list_sessions'))

# --- Socket.IO Events ---
@socketio.on('connect')
def handle_connect():
    print(f"--- SOCKETIO: Client connected: {request.sid}")

@socketio.on('disconnect')
def handle_disconnect():
    print(f"--- SOCKETIO: Client disconnected: {request.sid}")
    session_id = sid_to_session.pop(request.sid, None)
    global dialogue_flow
    if session_id and dialogue_flow and getattr(dialogue_flow, "session_id", None) == session_id:
        # Bước 1: Yêu cầu flow hủy bỏ các tác vụ đang chạy
        try:
            print(f"--- SOCKETIO: Attempting to cancel dialogue flow for session {session_id}...")
            if hasattr(dialogue_flow, 'cancel'): # Kiểm tra xem phương thức cancel có tồn tại không
                 dialogue_flow.cancel()
                 print(f"--- SOCKETIO: Dialogue flow for session {session_id} cancellation requested.")
            else:
                 print(f"--- SOCKETIO: Dialogue flow instance for session {session_id} does not have a 'cancel' method.")

        except Exception as e:
            print(f"!!! ERROR requesting cancellation for {session_id}: {e}")
            traceback.print_exc()

        # Bước 2: Lưu session data (có thể cần đợi cancel hoàn tất hoặc lưu trạng thái hiện tại)
        try:
            # dialogue_flow vẫn trỏ đến đối tượng này, ngay cả khi nó đang trong quá trình hủy
            save_session_data(dialogue_flow.export_session_data())
        except Exception as e:
            print(f"!!! ERROR saving session data for {session_id} on disconnect: {e}")
            traceback.print_exc()

        # Bước 3: Giải phóng biến toàn cục
        dialogue_flow = None
    elif session_id:
        print(f"--- SOCKETIO: Client disconnected from session {session_id}, but it was not the active flow.")
    else:
        print(f"--- SOCKETIO: Client disconnected, no active session found for sid {request.sid}.")

@socketio.on('join')
def handle_join(data):
    """Client joins a specific session room"""
    session_id = data.get('session_id')
    if not session_id:
        emit('navigate', {'url': url_for('list_sessions')}, room=request.sid)
        return
    
    # Check if session exists
    with app.app_context():
        db = database.get_db()
        if not db.execute('SELECT 1 FROM sessions WHERE session_id = ?', (session_id,)).fetchone():
            emit('navigate', {'url': url_for('list_sessions')}, room=request.sid)
            return
    
    join_room(session_id)
    sid_to_session[request.sid] = session_id  # Ghi nhớ mapping này
    print(f"--- SOCKETIO [{session_id}]: Client {request.sid} joined room")
    emit('joined', {'status': 'success', 'session_id': session_id}, room=request.sid)

@socketio.on('leave')
def handle_leave(data):
    """Client leaves a specific session room"""
    session_id = data.get('session_id')
    if session_id:
        # Lưu session data khi rời phòng
        if dialogue_flow and getattr(dialogue_flow, "session_id", None) == session_id:
            save_session_data(dialogue_flow.export_session_data())
        leave_room(session_id)
        sid_to_session.pop(request.sid, None)  # Xóa mapping khi rời phòng
        print(f"--- SOCKETIO [{session_id}]: Client {request.sid} left room")

@socketio.on('new_message')
def handle_message(data):
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
        if not db.execute('SELECT 1 FROM sessions WHERE session_id = ?', (session_id,)).fetchone():
            emit('error', {'message': 'Session not found'})
            return
    
    sender_id = f"user-{sender_name.lower().replace(' ', '-')}"
    print(f"--- SOCKETIO [{session_id}]: Received message from '{sender_name}' ({sender_id}): {text}")

    global dialogue_flow
    agent_names = dialogue_flow.state.participants if dialogue_flow else []

    # Only broadcast the message if the sender is not an agent (means it's a user message)
    if sender_name not in agent_names: 
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
    if dialogue_flow:
        try:
            print("--- SOCKETIO: Passing message to dialogue flow...")
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
    keywords = request.form.get('keywords', '').strip()
    # --- Lấy giá trị script từ client ---
    script_from_client = request.form.get('script', None)
    
    # Nếu client gửi script=default thì xử lý riêng
    if script_from_client == 'default':
        default_problem_id = '1'
        problem_id = default_problem_id
    


    if problem_id not in problem_list_data:
        flash("Vui lòng chọn một bài toán hợp lệ.", "error")
        return redirect(url_for('select_problem_page'))

    problem_data = problem_list_data[problem_id]
    problem_text = problem_data.get('problem', '')
    print(f"--- APP: Problem text: {problem_text}")
    solution_text = problem_data.get('solution', '') # Assuming solution is available for script generation

    if not problem_text:
        flash("Không tìm thấy nội dung bài toán đã chọn.", "error")
        return redirect(url_for('select_problem_page'))

    keywords_list = [kw.strip() for kw in keywords.split(",") if kw.strip()]

    if script_from_client == 'default':
        script = load_yaml(base_script_path)
        roles = load_yaml(base_participants_path)
        create_agent_config(
            base_participants_path,
            meta_agents_path,
            output_path
        )
    else:
        try:
            kwargs = {
                "problem": problem_text,
                "solution": solution_text,
                "keywords": keywords_list
            }
            script, roles = generate_script_and_roles(folder_path, **kwargs)
            
            # Create agent config from dynamic script and roles for this session
            create_agent_config(
                dynamic_participants_path,
                meta_agents_path,
                output_path
            )
        except Exception as e:
            print(f"!!! ERROR generating or saving script/personas: {e}")
            traceback.print_exc()
            flash("Có lỗi xảy ra trong quá trình tạo kịch bản. Sử dụng kịch bản mặc định (nếu có).", "warning")



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
        conversation = f"TIME={time.time()} | CON#0 | SENDER=System | TEXT=Chào mừng các bạn đến với lớp học. Bài toán của chúng ta là: {problem_text}\n"
        inner_thought = [] # Initialize as an empty list, not a string "[]"
        turn_number = 0
        session_data = {
            "session_id": session_id,
            "user_name": username,
            "problem": problem_text,
            "script": script,
            "roles": roles,
            "current_stage_id": current_stage_id,
            "conversation": conversation,
            "log_file": log_file,
            "stage_state": stage_state,
            "inner_thought": inner_thought, # Use the list here
            "turn_number": turn_number
        }
        # Call the new create_session function instead of save_session_data
        create_session(session_data)
        print(f"--- APP: Created new session {session_id} for user {username} (problem {problem_id}) ---")
        
        return redirect(url_for('chat_interface', session_id=session_id))
    
    except Exception as e:
        print(f"!!! ERROR creating new session in DB: {e}")
        traceback.print_exc()
        db.rollback()
        flash("Có lỗi xảy ra khi tạo phiên trò chuyện mới.", "error")
        return redirect(url_for('select_problem_page'))

# Biến cờ để kiểm soát việc tắt
shutdown_flag = False

async def shutdown():
    global shutdown_flag
    shutdown_flag = True
    print("--- APP: Shutting down gracefully...")
    if dialogue_flow:
        save_session_data(dialogue_flow.export_session_data())
    print("--- APP: Shutdown complete.")

def signal_handler(sig, frame):
    print("--- APP: Received signal, shutting down...")
    asyncio.create_task(shutdown())

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)  # Bắt tín hiệu Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler) # Bắt tín hiệu tắt khác

    try:
        socketio.run(app, debug=True, use_reloader=False)
    except Exception as e:
        print(f"!!! ERROR starting socketio: {e}")
        traceback.print_exc()

