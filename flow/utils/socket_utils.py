import time
from flask_socketio import emit

def send_message_via_socketio(message_data, session_id):
    """
    Send a message via Socket.IO to clients in the session room.
    
    Args:
        message_data (dict): The message data to send
        session_id (str): The session ID to send the message to
    """
    # Emit the message to the specific room (session)
    emit('new_message', {
        'source': message_data['source'],
        'content': message_data['content'],
        'timestamp': int(time.time() * 1000)
    }, room=session_id, namespace='/')

def send_agent_status_via_socketio(agent_name, status, session_id):
    """
    Send an agent status update via Socket.IO to clients in the session room.
    
    Args:
        agent_name (str): The name of the agent
        status (str): The status of the agent ('idle', 'thinking', 'typing')
        session_id (str): The session ID to send the status update to
    """
    status_data = {
        'source': 'system',
        'content': {
            'agent_name': agent_name,
            'status': status
        },
        'timestamp': int(time.time() * 1000)
    }
    
    emit('agent_status', status_data, room=session_id, namespace='/')

def send_stage_update_via_socketio(stage_data, session_id):
    """
    Send a stage update via Socket.IO to clients in the session room.
    
    Args:
        stage_data (dict): The stage data to send
        session_id (str): The session ID to send the stage update to
    """
    update_data = {
        'source': 'system',
        'content': stage_data,
        'timestamp': int(time.time() * 1000)
    }
    
    emit('stage_update', update_data, room=session_id, namespace='/')
    
def send_system_status(message, session_id):
    """
    Send a system status message via Socket.IO to clients in the session room.
    
    Args:
        message (str): The status message
        session_id (str): The session ID to send the status to
    """
    status_data = {
        'source': 'system',
        'content': {
            'status': message
        },
        'timestamp': int(time.time() * 1000)
    }
    
    emit('system_status', status_data, room=session_id, namespace='/')