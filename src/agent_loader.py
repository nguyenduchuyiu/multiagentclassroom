import yaml
from utils.helpers import generate_uuid
from core.base_agent import BaseAgent

class AgentLoader:
    def __init__(self, agent_config_path: str, task_config_path: str, event_manager, conversation):
        """
        Load agent and task configurations from YAML files and instantiate BaseAgent with tasks.

        :param agent_config_path: Path to agents.yaml
        :param task_config_path: Path to tasks.yaml
        :param event_manager: EventManager instance
        :param conversation: Conversation instance
        """
        self.agent_config_path = agent_config_path
        self.task_config_path = task_config_path
        self.event_manager = event_manager
        self.conversation = conversation
        self.agents = {}
        self._load_config()

    def _load_config(self):
        # Load agents and tasks from YAML
        with open(self.agent_config_path, 'r', encoding='utf-8') as f:
            agents_cfg = yaml.safe_load(f)
        with open(self.task_config_path, 'r', encoding='utf-8') as f:
            tasks_cfg = yaml.safe_load(f)

        # Group tasks by agent name
        tasks_by_agent = {}
        for task_name, task in tasks_cfg.items():
            agent_name = task.get('agent')
            if not agent_name:
                continue
            agent_tasks = tasks_by_agent.setdefault(agent_name, {})
            agent_tasks[task_name] = {
                'description': task.get('description'),
            }

        # Instantiate agents
        for agent_name, cfg in agents_cfg.items():
            agent_id = generate_uuid()
            # Extract persona fields
            role = cfg.pop('role', '')
            backstory = cfg.pop('backstory', '')
            goal = cfg.pop('goal', '')
            # Build system instruction if needed
            system_instruction = f"Role: {role}\nGoal: {goal}\nBackstory: {backstory}".strip()
            # cfg['system_instruction'] = system_instruction
            cfg['tasks'] = tasks_by_agent.get(agent_name, {})
            cfg['name'] = agent_name

            # Prepare init kwargs
            init_kwargs = {
                'agent_id': agent_id,
                'event_manager': self.event_manager,
                'conversation': self.conversation,
                'system_instruction': system_instruction,
                **cfg
            }
            # Instantiate and store
            agent = BaseAgent(**init_kwargs)
            self.agents[agent_name] = agent

    def get_agents(self):
        """
        :return: dict of agent_name -> BaseAgent instance
        """
        return self.agents


