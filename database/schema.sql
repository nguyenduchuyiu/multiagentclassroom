-- schema.sql
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS sessions;

CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,      -- Unique UUID for the session
  user_name TEXT NOT NULL,          -- User who started the session
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  problem TEXT,                     -- Problem context for this session
  script TEXT,                      -- Generated script for the session
  roles TEXT,                       -- Roles of participants as JSON
  current_stage_id TEXT,            -- Current stage ID in the script
  conversation TEXT,                -- Conversation history
  log_file TEXT,                    -- Path to the log file
  stage_state TEXT,                 -- State of the current stage as string of JSON
  inner_thought TEXT                 -- Agent's inner thoughts as string of lists
);

CREATE TABLE events (
  event_id TEXT PRIMARY KEY,        -- Unique UUID for the event
  session_id TEXT NOT NULL,         -- Foreign key to sessions table
  timestamp INTEGER NOT NULL,       -- Milliseconds since epoch (compatible with JS Date.now())
  event_type TEXT NOT NULL,         -- e.g., 'new_message', 'agent_status', 'system_message'
  source TEXT NOT NULL,             -- e.g., 'user-id', 'agent-uuid', 'System', 'PhaseManager'
  content JSON_TEXT NOT NULL,       -- Event payload as JSON text
  metadata JSON_TEXT,               -- Additional context as JSON text
  FOREIGN KEY (session_id) REFERENCES sessions (session_id)
);

-- Optional: Add indexes for faster querying
CREATE INDEX idx_events_session_id_timestamp ON events (session_id, timestamp);