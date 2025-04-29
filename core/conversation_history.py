# core/conversation_history.py
import time
import uuid
import threading
import json
from flask import g # Use Flask's application context for DB access
from database.database import get_db # Import the get_db function

class ConversationHistory:
    def __init__(self):
        # No longer holds data directly, interacts with DB via get_db()
        self._lock = threading.Lock() # Still useful for potential future complex ops
        print("--- CONV_HIST: Initialized (DB Interaction Mode) ---")

    def add_event(self, session_id: str, event_type: str, source: str, content: dict, metadata: dict = None):
        """Adds a structured event to the database for a specific session."""
        if not session_id:
             print("!!! ERROR [ConvHistory]: Attempted to add event without session_id.")
             return None

        event_id = str(uuid.uuid4())
        timestamp = int(time.time() * 1000) # Milliseconds
        metadata = metadata or {}

        db = get_db()
        try:
            db.execute(
                """
                INSERT INTO events (event_id, session_id, timestamp, event_type, source, content, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, session_id, timestamp, event_type, source, content, metadata) # Pass dicts directly (adapter handles JSON)
            )
            db.commit()
            print(f"HIST DB LOG [{session_id}]: [{event_type}] Source={source}") # Log to console

            # Return the structure consistent with previous version for immediate use
            return {
                "event_id": event_id,
                "session_id": session_id, # Include session_id
                "timestamp": timestamp,
                "event_type": event_type,
                "source": source,
                "content": content,
                "metadata": metadata
            }
        except Exception as e:
            print(f"!!! ERROR [ConvHistory]: Failed to add event to DB for session {session_id}: {e}")
            db.rollback() # Rollback on error
            return None


    def get_history(self, session_id: str, count=None):
        """Retrieves event history for a specific session from the database."""
        if not session_id:
             print("!!! ERROR [ConvHistory]: Attempted to get history without session_id.")
             return []

        db = get_db()
        query = "SELECT event_id, session_id, timestamp, event_type, source, content, metadata FROM events WHERE session_id = ? ORDER BY timestamp ASC"
        params = [session_id]

        if count:
            # Note: Efficient limiting might depend on DB. For SQLite, getting all and slicing might be okay for moderate history.
            # For large histories, consider OFFSET/LIMIT or window functions if performance is critical.
            # Let's fetch all and slice in Python for simplicity here.
             pass # Fetch all first

        try:
            cursor = db.execute(query, params)
            # Convert rows to dictionaries (using sqlite3.Row factory helps)
            # The JSON_TEXT converter handles 'content' and 'metadata'
            history = [dict(row) for row in cursor.fetchall()]

            if count:
                return history[-count:] # Slice the last 'count' items
            else:
                return history
        except Exception as e:
            print(f"!!! ERROR [ConvHistory]: Failed to get history from DB for session {session_id}: {e}")
            return []


    def get_last_event(self, session_id: str):
         """Retrieves the most recent event for a specific session."""
         if not session_id:
             print("!!! ERROR [ConvHistory]: Attempted to get last event without session_id.")
             return None

         db = get_db()
         query = "SELECT event_id, session_id, timestamp, event_type, source, content, metadata FROM events WHERE session_id = ? ORDER BY timestamp DESC LIMIT 1"
         params = [session_id]
         try:
             cursor = db.execute(query, params)
             row = cursor.fetchone()
             return dict(row) if row else None
         except Exception as e:
             print(f"!!! ERROR [ConvHistory]: Failed to get last event from DB for session {session_id}: {e}")
             return None