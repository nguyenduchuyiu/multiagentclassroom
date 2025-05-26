# core/agent_manager.py
import concurrent.futures
import traceback
from typing import List, Dict, Any
from core.agent_mind import AgentMind
from core.persona import Persona
from core.conversation_history import ConversationHistory
from core.stage_management.conversation_phase_orchestrator import ConversationPhaseOrchestrator
from services.llm_service import LLMService
from utils.loaders import load_personas_from_yaml
from flask import Flask

class AgentManager:
    def __init__(self, persona_config_path: str, problem_description: str, llm_service: LLMService, app_instance: Flask):
        self.problem = problem_description
        self.llm_service = llm_service
        self.app = app_instance # Store app instance
        self.agents: Dict[str, AgentMind] = self._load_agents(persona_config_path)
        # Adjust max_workers if needed, default to number of agents
        num_workers = len(self.agents) if self.agents else 1
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=num_workers)
        print(f"--- AGENT_MGR: Initialized with {len(self.agents)} agents and {num_workers} workers.")

    def _load_agents(self, config_path: str) -> Dict[str, AgentMind]:
        agents = {}
        try:
            personas = load_personas_from_yaml(config_path)
            if not personas:
                 print(f"!!! WARN [AgentManager]: No personas loaded from {config_path}.")
                 return {}
            for agent_id, persona in personas.items():
                 # Pass self.app to AgentMind constructor
                 agents[agent_id] = AgentMind(persona, self.problem, self.llm_service, self.app)
                 print(f"--- AGENT_MGR: Loaded AgentMind for {persona.name} ({agent_id})")
        except Exception as e:
            print(f"!!! ERROR [AgentManager]: Failed to load agents from {config_path}: {e}")
            traceback.print_exc()
        return agents

    def get_all_agent_ids(self) -> List[str]:
        return list(self.agents.keys())

    def get_agent_mind(self, agent_id: str) -> AgentMind | None:
        return self.agents.get(agent_id)

    def request_thinking(self,
                         session_id: str,
                         triggering_event: Dict,
                         conversation_history: ConversationHistory,
                         phase_manager: ConversationPhaseOrchestrator) -> List[Dict[str, Any]]:
        """Triggers thinking, passing task status."""
        log_prefix = f"--- AGENT_MGR [{session_id}]"
        # print(f"{log_prefix}: Requesting thinking for all agents (Event: {triggering_event['event_id']})")
        futures = []
        for agent_id, agent_mind in self.agents.items():
            future = self.executor.submit(
                agent_mind.think,
                session_id=session_id,
                triggering_event=triggering_event,
                conversation_history=conversation_history,
                phase_manager=phase_manager,
            )
            futures.append(future)

        results = []
        # Wait for all futures to complete
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                print(f"!!! ERROR [{log_prefix}]: Agent thinking task failed: {e}")
                traceback.print_exc() # Print full traceback for thread errors

        print(f"{log_prefix}: Collected {len(results)} thinking results.")
        return results

    def cleanup(self):
        """Shuts down the thread pool executor."""
        print("--- AGENT_MGR: Shutting down thread pool executor...")
        # Wait for pending tasks to complete before shutting down
        self.executor.shutdown(wait=True)
        print("--- AGENT_MGR: Executor shut down.")