# chatcollab_app/database/database.py
import sqlite3
import click
from flask import current_app, g
from flask.cli import with_appcontext
import json # For storing content/metadata

DATABASE = 'chat_sessions.db'

def get_db():
    """Connects to the specific database."""
    if 'db' not in g:
        g.db = sqlite3.connect(
            DATABASE,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row # Access columns by name
    return g.db

def close_db(e=None):
    """Closes the database connection."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Clears existing data and creates new tables."""
    db = get_db()
    # Read schema file
    with current_app.open_resource('database/schema.sql') as f:
        db.executescript(f.read().decode('utf8'))
    print("Initialized the database.")

@click.command('init-db')
@with_appcontext
def init_db_command():
    """CLI command to initialize the database."""
    init_db()

def init_app(app):
    """Register database functions with the Flask app."""
    app.teardown_appcontext(close_db) # Close DB after each request
    app.cli.add_command(init_db_command) # Add `flask init-db` command

# --- Helper functions for JSON storage ---
def adapt_dict_to_text(data_dict):
    """Adapt Python dict to TEXT for SQLite storage."""
    return json.dumps(data_dict)

def convert_text_to_dict(text_data):
    """Convert TEXT from SQLite back to Python dict."""
    if text_data is None:
        return None
    return json.loads(text_data)

# Register the adapters
sqlite3.register_adapter(dict, adapt_dict_to_text)
sqlite3.register_converter("JSON_TEXT", convert_text_to_dict) # Use custom type name