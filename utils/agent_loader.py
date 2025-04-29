import yaml
from core.base_agent import DEFAULT_PROMPT_TEMPLATE, BaseAgent, DefaultIOHandler
from utils.helpers import generate_uuid


class AgentLoader:
    def __init__(self,
                 agent_config_path: str,
                 task_config_path: str,
                 event_manager,
                 conversation):
        self.agent_config_path = agent_config_path
        self.task_config_path = task_config_path
        self.event_manager = event_manager
        self.conversation = conversation
        self.agents = {}
        self._load_config()

    def _load_config(self):
        # Đọc config từ YAML
        with open(self.agent_config_path, 'r', encoding='utf-8') as f:
            agents_cfg = yaml.safe_load(f)
        with open(self.task_config_path, 'r', encoding='utf-8') as f:
            tasks_cfg = yaml.safe_load(f)

        # Gom tasks theo agent
        tasks_by_agent = {}
        for name, info in tasks_cfg.items():
            ag = info.get('agent')
            if not ag:
                continue
            tasks_by_agent.setdefault(ag, {})[name] = {
                'description': info.get('description')
            }

        # Instantiate agents
        for agent_name, props in agents_cfg.items():
            agent_id = generate_uuid()
            role = props.get('role', '')
            goal = props.get('goal', '')
            backstory = props.get('backstory', '')
            system_instruction = f"Role: {role}\nGoal: {goal}\nBackstory: {backstory}".strip()

            agent_tasks = tasks_by_agent.get(agent_name, {})

            prompt_template = props.get('prompt_template', DEFAULT_PROMPT_TEMPLATE)
            io_handler = DefaultIOHandler(prompt_template)

            agent = BaseAgent(
                agent_id=agent_id,
                event_manager=self.event_manager,
                conversation=self.conversation,
                system_instruction=system_instruction,
                tasks=agent_tasks,
                prompt_template=prompt_template,
                io_handler=io_handler,
                name=agent_name,
                model=props.get('model')
            )
            self.agents[agent_name] = agent

    def get_agents(self):
        return self.agents