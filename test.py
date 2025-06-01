import sqlite3

session_id = '717d217b-f4d8-4718-9742-d91524f251d7'
new_stage_id = "4"

try:
    conn = sqlite3.connect('chat_sessions.db')
    cursor = conn.cursor()

    cursor.execute("UPDATE sessions SET current_stage_id = ? WHERE session_id = ?", (new_stage_id, session_id))
    conn.commit()

    print(f"Successfully updated current_stage_id to {new_stage_id} for session {session_id}")

except sqlite3.Error as e:
    print(f"An error occurred: {e}")

finally:
    if conn:
        conn.close()
