# ChatCollab - Multi-Agent Collaborative Chat Framework

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Flask Version](https://img.shields.io/badge/flask-2.x%2B-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)](LICENSE) <!-- Add a LICENSE file -->

ChatCollab là một framework ứng dụng web được xây dựng bằng Flask, cho phép mô phỏng các cuộc trò chuyện hợp tác giữa nhiều AI agent và người dùng. Các agent được định cấu hình thông qua file YAML, tương tác với nhau và với người dùng thông qua một giao diện chat, và sử dụng một dịch vụ LLM (Large Language Model) bên ngoài để tạo phản hồi. Cập nhật trạng thái và tin nhắn mới được truyền tải theo thời gian thực bằng Server-Sent Events (SSE).

(ChatCollab is a web application framework built with Flask that simulates collaborative conversations between multiple AI agents and a human user. Agents are configured via YAML files, interact with each other and the user through a chat interface, and utilize an external LLM service to generate responses. Real-time updates for new messages and agent statuses are delivered using Server-Sent Events (SSE).)

## Features

*   **Multi-Agent Simulation:** Hỗ trợ nhiều AI agent cùng tham gia vào một cuộc trò chuyện.
*   **Configurable Agents:** Định nghĩa dễ dàng các agent (vai trò, mục tiêu, backstory, cấu hình LLM) thông qua file `config/agents.yaml`.
*   **Task Assignment:** Định nghĩa các nhiệm vụ (tasks) cụ thể cho agent trong `config/tasks.yaml`.
*   **Real-time Communication:** Sử dụng Server-Sent Events (SSE) để cập nhật giao diện người dùng ngay lập tức khi có tin nhắn mới hoặc trạng thái agent thay đổi.
*   **LLM Integration:** Tích hợp với các dịch vụ LLM (Large Language Model) thông qua lớp trừu tượng `LLMService`.
*   **Conversation Management:** Lưu trữ và truy xuất lịch sử cuộc trò chuyện.
*   **Agent Status Tracking:** Hiển thị trạng thái hiện tại của agent (idle, thinking, typing) trên giao diện.
*   **User Interaction:** Người dùng có thể tham gia trò chuyện, cung cấp tên của mình.
*   **Web Interface:** Giao diện người dùng cơ bản được xây dựng bằng HTML, CSS, và JavaScript.
*   **Thread-Safe Operations:** Sử dụng locks để đảm bảo an toàn khi nhiều agent hoạt động đồng thời.

## Technology Stack

*   **Backend:** Python 3.9+, Flask, Flask-CORS
*   **Frontend:** HTML5, CSS3, JavaScript (Vanilla)
*   **Configuration:** YAML (PyYAML)
*   **Real-time:** Server-Sent Events (SSE)
*   **LLM Interaction:** Abstracted via `services/llm_service.py` (requires specific LLM library like `openai`, `google-generativeai`, etc., depending on implementation)

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

4.  **Configure Environment Variables:**
    *   Copy the example environment file:
        ```bash
        cp .env.example .env
        ```
    *   Edit the `.env` file and add your LLM API key and any other necessary configuration for `LLMService`.
        ```dotenv
        # .env
        # Example for OpenAI
        LLM_API_KEY="your_openai_api_key_here"
        # LLM_BASE_URL="your_custom_openai_compatible_endpoint" # Optional
        # LLM_MODEL_NAME="gpt-3.5-turbo" # Default model used by LLMService if not in agents.yaml

        # Example for other services might need different variables
        # OTHER_LLM_API_KEY="your_other_key"
        ```
    *   The `LLMService` class needs to be implemented to read these variables (e.g., using `os.getenv`).

## Configuration

1.  **Agents (`config/agents.yaml`):**
    *   Define each agent by a unique name (e.g., `CoderAI`, `ManagerAI`).
    *   Specify `role`, `goal`, `backstory` to form the agent's persona and system prompt.
    *   Configure LLM parameters specific to the agent (e.g., `model`, `temperature`, `max_tokens`) which will be passed to `LLMService`. If not specified, `LLMService` might use defaults or environment variables.

2.  **Tasks (`config/tasks.yaml`):**
    *   Define available tasks with a `description`.
    *   Assign each task to an `agent` by name (matching a name in `agents.yaml`).
    *   The agent's prompt includes its assigned tasks.

3.  **LLM Service (`services/llm_service.py`):**
    *   This class needs to be implemented to handle communication with your chosen LLM provider (OpenAI, Google Gemini, local model, etc.).
    *   It should use the API key from environment variables and accept model/generation parameters.

## Running the Application

1.  **Ensure your virtual environment is activated.**
2.  **Make sure the `.env` file is configured correctly.**
3.  **Start the Flask development server:**
    ```bash
    flask run
    # Or directly using python:
    # python app.py
    ```
4.  **Open your web browser** and navigate to `http://127.0.0.1:5000` (or the address provided by Flask).
5.  You will be prompted to enter your name.
6.  Start chatting! Your messages will trigger the agents based on the `EventManager` logic.

## How It Works

1.  **User Interaction:** The user enters a name (stored in localStorage) and sends messages via the web UI.
2.  **Backend Receives Message:** The Flask `/send_message` endpoint receives the message text and the sender's name.
3.  **Conversation Update:** The message is added to the `Conversation` log.
4.  **Event Broadcast (User):** The `EventManager` broadcasts the new user message via SSE to all connected clients (including the sender's browser).
5.  **Agent Triggering:** The `EventManager` also notifies all subscribed AI agents (except the sender, if it were an agent) about the new message.
6.  **Agent Processing:** Each triggered agent (`BaseAgent` instance) runs its `process_new_event` method (typically in a separate thread):
    *   Sets status to "thinking" (broadcast via SSE).
    *   Calls `_think()`:
        *   Retrieves recent history from `Conversation`.
        *   Constructs a prompt using its system instruction, assigned tasks, conversation history, and potentially dynamic context.
        *   Calls `_llm_service.generate()` with the prompt and agent-specific config.
    *   Receives the response from the LLM.
    *   Calls `_decide_action()` to determine if the response is actionable (not "NO_RESPONSE").
    *   If actionable:
        *   Sets status to "typing" (broadcast via SSE).
        *   Simulates thinking/typing delays.
        *   Adds its response message(s) to the `Conversation` log (using its `agent_id` as sender).
        *   Broadcasts the new AI message(s) via `EventManager` (payload includes `agent_id` as `sender` and `agent_name` as `sender_name`).
    *   Sets status back to "idle" (broadcast via SSE).
7.  **Frontend Updates:** The JavaScript client receives `new_message` and `agent_status` events via SSE and updates the chat display and participant status list accordingly.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues. (Add more specific guidelines if desired).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details. (Create a `LICENSE` file with the MIT license text).
