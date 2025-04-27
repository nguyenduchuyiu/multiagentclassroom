
from src.agent_loader import AgentLoader
from core.conversation import Conversation
from core.event_manager import EventManager
from core.base_agent import BaseAgent
env = EventManager()
conv = Conversation()

loader = AgentLoader('config/agents.yaml', 'config/tasks.yaml', env, conv)
agents = loader.get_agents()
khanh = agents['Khánh']
# print(khanh.ge) 
prompt = '''this is '''

def refine(prompt, **kwargs):
    return prompt.format(**kwargs)

result = refine(prompt, name="huy")
print(result)
