# core/agent_manager.py
import concurrent.futures
import traceback
from typing import List, Dict, Any
from core.agent_mind import AgentMind
from core.persona import Persona
from core.conversation_history import ConversationHistory
from core.conversation_phase_manager import ConversationPhaseManager
from services.llm_service import LLMService
from utils.loaders import load_personas_from_yaml
from flask import Flask

class AgentManager:
    def __init__(self, persona_config_path: str, problem_description: str, llm_service: LLMService, app_instance: Flask):
        self.problem = problem_description
        self.llm_service = llm_service
        self.app = app_instance 
        self.agents: Dict[str, AgentMind] = self._load_agents(persona_config_path)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(self.agents) or 1)

    def _load_agents(self, config_path: str) -> Dict[str, AgentMind]:
        agents = {}
        try:
            personas = load_personas_from_yaml(config_path)
            for agent_id, persona in personas.items():
                # <<< Add Debug Print >>>
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


    # <<< Add session_id parameter >>>
    def request_thinking(self,
                         session_id: str, # Added
                         triggering_event: Dict,
                         conversation_history: ConversationHistory,
                         phase_manager: ConversationPhaseManager) -> List[Dict[str, Any]]:
        """
        Triggers the thinking process for all agents in parallel for a specific session.
        """
        print(f"--- AGENT_MGR [{session_id}]: Requesting thinking for all agents regarding event: {triggering_event['event_id']}")
        futures = []
        for agent_id, agent_mind in self.agents.items():
            # <<< Pass session_id to agent_mind.think >>>
            future = self.executor.submit(
                agent_mind.think,
                session_id=session_id, # Pass session id
                triggering_event=triggering_event,
                conversation_history=conversation_history,
                phase_manager=phase_manager
            )
            futures.append(future)

        results = []
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                # Include session_id in error log
                print(f"!!! ERROR [AgentManager - {session_id}]: Agent thinking task failed: {e}")
                traceback.print_exc()

        print(f"--- AGENT_MGR [{session_id}]: Collected {len(results)} thinking results.")
        return results

    def cleanup(self):
        # ... (remains the same) ...
        print("--- AGENT_MGR: Shutting down thread pool executor...")
        self.executor.shutdown(wait=True)
        print("--- AGENT_MGR: Executor shut down.")