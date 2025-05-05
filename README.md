# ChatCollab Refactored - Multi-Agent Collaborative Chat Framework

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask Version](https://img.shields.io/badge/flask-2.x%2B-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)](LICENSE) <!-- Add a LICENSE file -->

ChatCollab is a web application framework built with Flask, designed to simulate and facilitate structured, collaborative problem-solving conversations between multiple AI agents and a human user. Agents, defined by personas and tasks in YAML files, interact within distinct conversation phases, guided by an event-driven architecture. The system uses an external LLM service for agent intelligence and real-time Server-Sent Events (SSE) for UI updates. Session management with database persistence allows users to create and revisit conversations.

## Key Concepts & Features

*   **Event-Driven Architecture:** Core interactions are managed through triggers and events handled by the `InteractionCoordinator`.
*   **Multi-Agent Collaboration:** Supports multiple AI agents defined in `config/personas.yaml`.
*   **Structured Conversation Flow:** Utilizes a `ConversationPhaseManager` to guide the discussion through predefined stages (defined in `config/phases.yaml`) based on the problem context and conversation history. Task completion within phases can be tracked.
*   **Sophisticated Agent Logic (`AgentMind`):** Each agent performs an "inner thought" process based on its persona, conversation history, current phase, and assigned tasks before deciding to speak or listen.
*   **Dynamic Speaker Selection (`SpeakerSelector`):** Evaluates agents' intentions to speak based on internal drive and external context appropriateness using LLM-based scoring, selecting the most suitable agent for the next turn.
*   **Natural Interaction Simulation (`BehaviorExecutor`):** Executes agent actions (speaking) with simulated typing delays.
*   **Session Management & Persistence:**
    *   Users can create distinct chat sessions.
    *   Sessions and event history are stored in an SQLite database (`chat_sessions.db`).
    *   Allows revisiting past conversations.
*   **Database Integration:** Uses Flask-SQLAlchemy patterns (via custom `database.py`) for managing the SQLite database.
*   **Real-time Communication (SSE):** Server-Sent Events deliver new messages and agent status updates (`idle`, `thinking`, `typing`) instantly to the web interface.
*   **LLM Integration:** Connects to Large Language Models (like Google Gemini) via `services/llm_service.py`.
*   **Configurable Context:** Problem description and solution context loaded from `config/problem_context.yaml`.
*   **Thread Safety:** Employs threading and locks for concurrent processing of agent thinking and actions.
*   **Modular Design:** Core functionalities are separated into distinct components (Coordinator, Orchestrator, Managers, Selector, Executor) for better maintainability and extensibility.

## Technology Stack

*   **Backend:** Python 3.10+, Flask, Flask-CORS
*   **Database:** SQLite (managed via Flask context)
*   **Frontend:** HTML5, CSS3, JavaScript (Vanilla), MathJax (for LaTeX rendering)
*   **Configuration:** YAML (PyYAML)
*   **Real-time:** Server-Sent Events (SSE)
*   **LLM Interaction:** `google-generativeai` (or other, via `services/llm_service.py`)
*   **Concurrency:** `threading`, `concurrent.futures`

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/nguyenduchuyiu/chatcollab_app 
    cd chatcollab_app
    ```

2.  **Create and activate a virtual environment (recommended):**
    ```bash
    python -m venv venv
    # On Windows
    .\venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Ensure `requirements.txt` includes Flask, Flask-CORS, google-generativeai, python-dotenv, PyYAML, requests, regex)*

4.  **Configure Environment Variables:**
    *   Create a `.env` file in the project root.
    *   Add your Google Generative AI API key:
        ```dotenv
        # .env
        GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY_HERE"
        FLASK_SECRET_KEY="your-strong-random-secret-key-for-flash-messages" # Add a secret key
        ```

5.  **Initialize the Database:**
    *   Run the Flask command *once* to create the database schema:
        ```bash
        flask init-db
        ```
    *   This will create the `chat_sessions.db` file.

## Configuration Files

*   **`config/personas.yaml`:** Define AI agent personas (name, role, goal, backstory, tasks, model). The name here is used for display and matching.
*   **`config/phases.yaml`:** Define the stages of the conversation. Each stage has a `name`, `description`, `tasks` (list of dicts with `id` and `description`), and `goals`. Task `id`s are used for tracking.
*   **`config/problem_context.yaml`:** Defines the `problem` description and optionally the `solution` description, loaded at startup.

## Running the Application

1.  **Ensure your virtual environment is activated.**
2.  **Verify `.env` is configured and the database is initialized.**
3.  **Start the Flask development server:**
    ```bash
    flask run
    # Or directly using python:
    # python app.py
    ```
4.  **Open your web browser** and navigate to `http://127.0.0.1:5000` (or the address provided).
5.  You will see a list of existing sessions (if any) and an option to start a new one.
6.  Enter your name and click "Start New Chat".
7.  You will be redirected to the chat interface for the newly created session.

## High-Level Workflow

1.  **User Accesses Root (`/`):** Sees the session list (`list_sessions.html`).
2.  **User Starts New Chat:** Submits name via POST to `/chat/new`.
    *   Backend creates a new session entry in the `sessions` table (with initial metadata).
    *   Adds an initial system message event to the `events` table for this session.
    *   Redirects user to `/chat/<new_session_id>`.
3.  **User Enters Chat Page (`/chat/<session_id>`):**
    *   Backend verifies session and renders `index.html`, passing session details and AI participant info.
    *   Frontend (`chat_interface.js`) connects to `/stream/<session_id>`.
    *   Frontend fetches initial history from `/history/<session_id>` and displays it.
4.  **User Sends Message:** POST to `/send_message/<session_id>`.
    *   Backend receives message, triggers `InteractionCoordinator.handle_external_trigger(session_id, ...)`.
    *   `InteractionCoordinator`: Logs event to DB, broadcasts message via SSE to clients connected to *this session*, triggers `ResponseOrchestrator`.
    *   `ResponseOrchestrator` (background thread, with app context):
        *   Calls `ConversationPhaseManager.get_phase_context(session_id, ...)` (which gets DB state, calls LLM for signal, returns phase info + task status).
        *   Calls `AgentManager.request_thinking(session_id, ..., task_status_prompt)` (spawns threads for each `AgentMind.think`).
        *   `AgentMind.think` (background thread, with app context): Gets history/phase, builds prompt (incl. task status), calls LLM, returns thought/intention.
        *   `ResponseOrchestrator`: Collects thinking results.
        *   Calls `SpeakerSelector.select_speaker(session_id, ...)` (calls LLM evaluator, returns selected agent/action).
        *   If an agent is selected: Calls `BehaviorExecutor.execute(session_id, ...)`.
    *   `BehaviorExecutor` (spawns background thread):
        *   Posts "typing" status via `InteractionCoordinator`.
        *   Calls `_generate_final_message` (builds prompt, calls LLM).
        *   Simulates typing delay (`time.sleep`).
        *   Calls `InteractionCoordinator.handle_internal_trigger(session_id, ...)` (with app context) to log the agent's message to DB and broadcast via SSE.
        *   Posts "idle" status via `InteractionCoordinator`.
5.  **Frontend Updates:** Receives `new_message` and `agent_status` events via SSE for its specific session and updates the UI.

## Contributing

Contributions are welcome! Please open an issue to discuss major changes or submit a pull request for bug fixes/improvements.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.