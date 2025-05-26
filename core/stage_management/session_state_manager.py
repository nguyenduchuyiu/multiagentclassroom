# core/stage_management/session_state_manager.py
import json
import traceback
from typing import Dict, List, Tuple
from flask import Flask
from database.database import get_db

class SessionStateManager:
    def __init__(self, app_instance: Flask):
        self.app = app_instance
        print(f"--- SessionStateManager: Initialized.")

    def get_session_state(self, session_id: str) -> Tuple[str, Dict[str, List[str]]]:
        with self.app.app_context():
            db = get_db()
            state_row = db.execute(
                "SELECT current_phase_id, metadata FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()

            if not state_row:
                print(f"!!! WARN [SessionStateManager - {session_id}]: Session not found in DB. Defaulting state.")
                return "1", {}

            last_known_phase_id = state_row['current_phase_id'] or "1"
            
            raw_db_metadata = state_row['metadata']
            metadata = {}
            if raw_db_metadata:
                if isinstance(raw_db_metadata, dict):
                    metadata = raw_db_metadata
                elif isinstance(raw_db_metadata, (str, bytes, bytearray)):
                    try:
                        metadata = json.loads(raw_db_metadata)
                    except json.JSONDecodeError:
                        print(f"!!! WARN [SessionStateManager - {session_id}]: Could not decode metadata JSON: '{raw_db_metadata}'. Defaulting metadata.")
                else:
                    print(f"!!! WARN [SessionStateManager - {session_id}]: Metadata from DB is of unexpected type: {type(raw_db_metadata)}. Defaulting metadata.")
            
            completed_tasks_map = metadata.get("completed_tasks", {})
            if not isinstance(completed_tasks_map, dict):
                print(f"!!! WARN [SessionStateManager - {session_id}]: 'completed_tasks' in metadata is not a dict: {completed_tasks_map}. Defaulting to empty dict.")
                completed_tasks_map = {}
            
            for phase_key in list(completed_tasks_map.keys()):
                if not isinstance(completed_tasks_map[phase_key], list):
                    print(f"!!! WARN [SessionStateManager - {session_id}]: Tasks for phase {phase_key} in DB metadata was not a list: {completed_tasks_map[phase_key]}. Correcting to empty list.")
                    completed_tasks_map[phase_key] = []
            return last_known_phase_id, completed_tasks_map

    def update_session_state(self, session_id: str, new_phase_id_to_set_in_db: str, completed_tasks_map_to_save: Dict[str, List[str]]):
        with self.app.app_context():
            db = get_db()
            current_metadata_row = db.execute("SELECT metadata FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            
            existing_metadata = {}
            if current_metadata_row and current_metadata_row['metadata']:
                raw_current_db_metadata = current_metadata_row['metadata']
                if isinstance(raw_current_db_metadata, dict):
                    existing_metadata = raw_current_db_metadata
                elif isinstance(raw_current_db_metadata, (str, bytes, bytearray)):
                    try:
                        existing_metadata = json.loads(raw_current_db_metadata)
                    except json.JSONDecodeError:
                        print(f"!!! WARN [SessionStateManager - {session_id}]: Could not decode existing metadata JSON during update: '{raw_current_db_metadata}'. Starting fresh metadata.")
                else:
                    print(f"!!! WARN [SessionStateManager - {session_id}]: Existing metadata from DB is of unexpected type during update: {type(raw_current_db_metadata)}. Starting fresh metadata.")

            if "completed_tasks" not in existing_metadata or not isinstance(existing_metadata["completed_tasks"], dict):
                 existing_metadata["completed_tasks"] = {}
            
            for phase_id, tasks in completed_tasks_map_to_save.items():
                if isinstance(tasks, list):
                    existing_metadata["completed_tasks"][phase_id] = list(set(str(t) for t in tasks))
                else:
                    print(f"!!! WARN [SessionStateManager - {session_id}]: Tasks for phase {phase_id} in completed_tasks_map_to_save is not a list: {tasks}. Retaining existing or initializing as empty list.")
                    if phase_id not in existing_metadata["completed_tasks"] or not isinstance(existing_metadata["completed_tasks"][phase_id], list):
                        existing_metadata["completed_tasks"][phase_id] = []
            try:
                db.execute(
                    "UPDATE sessions SET current_phase_id = ?, metadata = ? WHERE session_id = ?",
                    (new_phase_id_to_set_in_db, json.dumps(existing_metadata), session_id)
                )
                db.commit()
                print(f"--- SessionStateManager [{session_id}]: Updated session state in DB - Phase: {new_phase_id_to_set_in_db}, Metadata tasks: {existing_metadata.get('completed_tasks')}")
            except Exception as e:
                print(f"!!! ERROR [SessionStateManager - {session_id}]: Failed to update session state in DB: {e}")
                traceback.print_exc()
                db.rollback()

    def update_session_phase_id_in_db(self, session_id: str, new_phase_id: str):
        with self.app.app_context():
            try:
                db = get_db()
                db.execute(
                    "UPDATE sessions SET current_phase_id = ? WHERE session_id = ?",
                    (new_phase_id, session_id)
                )
                db.commit()
                print(f"--- SessionStateManager [{session_id}]: Updated session phase (only phase_id column) in DB to '{new_phase_id}'.")
            except Exception as e:
                print(f"!!! ERROR [SessionStateManager - {session_id}]: Failed to update session phase (only phase_id column) in DB: {e}")
                db.rollback()

    def get_current_phase_id_from_db(self, session_id: str) -> str:
        with self.app.app_context():
            db = get_db()
            session_data = db.execute(
                "SELECT current_phase_id FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()

            last_known_phase_id_from_db = "1" # Default
            if session_data and session_data['current_phase_id']:
                last_known_phase_id_from_db = session_data['current_phase_id']
            elif session_data: # current_phase_id is NULL in DB
                 print(f"!!! WARN [SessionStateManager (get_current_phase_id_from_db) - {session_id}]: current_phase_id is null in DB. Defaulting to '1' and updating DB.")
                 self.update_session_phase_id_in_db(session_id, last_known_phase_id_from_db) # Initialize it
            else: # No session row found
                 print(f"!!! ERROR [SessionStateManager (get_current_phase_id_from_db) - {session_id}]: Session data not found in DB. Defaulting phase to '1'.")
                 # Consider if a session should be created here or if an error should be raised.
                 # For now, it defaults and might attempt an update if a session_id was passed.
                 # If the session doesn't exist, update_session_phase_id_in_db might silently fail or error depending on DB setup.
                 # A robust solution might involve creating the session row if it's missing.
            return last_known_phase_id_from_db