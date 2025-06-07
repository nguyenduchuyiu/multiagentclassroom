# MultiAgentClassroom - Interactive Multi-Agent Learning Framework
See demo video below (may take some time to load): 
[![Demo](https://github.com/nguyenduchuyiu/multiagentclassroom/raw/main/demo.gif)](https://github.com/nguyenduchuyiu/multiagentclassroom/raw/main/demo.gif)

**MultiAgentClassroom** is a Flask-based web app for a dynamic **virtual learning environment**. It supports real-time discussions between a student and a system designed for **multiple AI agents** (e.g., tutors, peers) to foster collaborative problem-solving, guided discovery, and debate. The framework aims to simulate diverse classroom dynamics using a configurable **multi-agent system**.

---

## Overview

The app enables students to engage with educational content via an interactive chat interface, selecting problems, starting sessions, and interacting with AI-driven guidance. It uses SQLite for session persistence, MathJax for mathematical notation, and Server-Sent Events (SSE) for real-time updates.

**Key Features:**
- **Web Interface:** Problem selection, chat interface, session listing, and welcome page.
- **Session Management:** Create, store, and revisit sessions with unique IDs.
- **Real-time Communication:** SSE for dynamic updates .
- **Content Display:** Shows problems, learning stages, and participants (student + AI agents).
- **MathJax:** Renders LaTeX formulas.
- **Controls:** Restart sessions or export chats.

---

## Core Architecture

1. **Frontend & Backend:**
   - **Frontend** : Displays problems, chats, and progress, updated via SSE.
   - **Flask Backend**: Manages pages, sessions, database, and routes inputs to the multi-agent system.

2. **Multi-Agent System (Design Goal):**
   - **Learning Cycle:** Starts with student input or cues, storing context in SQLite.
   - **Agent Roles:** AI agents (e.g., Socratic Questioner) use YAML-defined personas (`config/personas.yaml`) to respond pedagogically.
   - **Coordination:** A Speaker Selector picks the best agent response based on learning goals.
   - **Response Delivery:** Selected agent's response is sent via SSE to the student and other agents.

3. **Configuration & Progress:**
   - **YAML Files:** Define personas (`personas.yaml`), learning phases (`phases.yaml`), and problems (`problems.yaml`).
   - **Dynamic Generation:** uses LLMs to create tailored personas/phases based on problems and keywords.
   - **Database:** Stores sessions and history in database.
   - **Environment:** `.env` secures API keys and Flask settings.

---

## Designing via YAML

1. **`config/personas.yaml`:** Define AI roles (e.g., Math Tutor, Socratic Guide) with goals and tasks.
   ```yaml
   SocraticTutor:
     role: "Guides via questioning."
     goal: "Enhance critical thinking."
     tasks: |
       - Ask probing questions.
       - Prompt reasoning.
   ```
2. **`config/phases.yaml`:** Structure learning stages with tasks and goals.
3. **`config/problem_context.yaml`:** List problems and solutions.

**Dynamic Option:** Generate YAMLs via LLMs based on problem and keywords.

---

## Installation

1. **Clone Repo**
   ```bash
   git clone https://github.com/nguyenduchuyiu/multiagentclassroom.git
   cd multiagentclassroom
   ```

2. **Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # macOS/Linux
   .\venv\Scripts\activate  # Windows
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set Environment**
   Copy `.env.example` to `.env`, add:
   ```dotenv
   GOOGLE_API_KEY="YOUR_KEY"
   FLASK_SECRET_KEY="YOUR_SECRET"
   ```

5. **Initialize Database**
   ```bash
   flask init-db
   ```

6. **Run**
   ```bash
   flask run
   ```
   Access at `http://127.0.0.1:5000`.

---
