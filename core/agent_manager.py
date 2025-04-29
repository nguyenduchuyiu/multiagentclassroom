# core/agent_manager.py
import concurrent.futures
import traceback
from typing import List, Dict, Any
from core.agent_mind import AgentMind
from core.persona import Persona
from core.conversation_history import ConversationHistory
from core.conversation_phase_manager import ConversationPhaseManager
from services.llm_service import LLMService # Needed to create AgentMind
from utils.loaders import load_personas_from_yaml # Assuming this exists

class AgentManager:
    def __init__(self, persona_config_path: str, problem_description: str, llm_service: LLMService): # Added problem_description
        self.problem = problem_description # Store problem
        self.llm_service = llm_service
        self.agents: Dict[str, AgentMind] = self._load_agents(persona_config_path)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(self.agents) or 1)

    def _load_agents(self, config_path: str) -> Dict[str, AgentMind]:
        agents = {}
        try:
            # Assuming load_personas_from_yaml is in utils.loaders
            from utils.loaders import load_personas_from_yaml
            personas = load_personas_from_yaml(config_path)
            for agent_id, persona in personas.items():
                 # Pass problem description to AgentMind constructor
                 agents[agent_id] = AgentMind(persona, self.problem, self.llm_service)
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
                         triggering_event: Dict,
                         conversation_history: ConversationHistory,
                         phase_manager: ConversationPhaseManager) -> List[Dict[str, Any]]:
        """
        Triggers the thinking process for all relevant agents in parallel
        and collects their results (thoughts, intentions, potential messages).
        """
        print(f"--- AGENT_MGR: Requesting thinking for all agents regarding event: {triggering_event['event_id']}")
        futures = []
        # Submit thinking tasks to the thread pool
        for agent_id, agent_mind in self.agents.items():
            # Add agent_id to the arguments if needed by think method, or rely on persona within agent_mind
            future = self.executor.submit(agent_mind.think, triggering_event, conversation_history, phase_manager)
            futures.append(future)

        results = []
        # Collect results as they complete
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                if result: # AgentMind might return None if skipped
                    results.append(result)
            except Exception as e:
                print(f"!!! ERROR [AgentManager]: Agent thinking task failed: {e}")
                traceback.print_exc()
                # Optionally add a failure marker to results

        print(f"--- AGENT_MGR: Collected {len(results)} thinking results.")
        return results

    def cleanup(self):
        """Shuts down the thread pool executor."""
        print("--- AGENT_MGR: Shutting down thread pool executor...")
        self.executor.shutdown(wait=True)
        print("--- AGENT_MGR: Executor shut down.")