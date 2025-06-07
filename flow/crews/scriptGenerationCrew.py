from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from dotenv import load_dotenv

load_dotenv()
import os
print(f"--- DEBUG: Loaded GOOGLE_API_KEY: {os.getenv('GOOGLE_API_KEY')}") # Thay 'OPENAI_API_KEY' bằng tên biến môi trường thực tế của bạn

@CrewBase
class ScriptWriter():
    """Script Writer Crew
        This crew is used to write the script for the classmate
        Include 2 agents and tasks:
            - ScriptWriter: Write the script for the classmate 
                - Task: write_script
            - RolesWriter: Write the roles for the classmate
                - Task: write_roles
        Input:
            - problem: The problem for the classmate
            - solution: The solution for the classmate
            - keywords: The keywords for the classmate
        Output:
            - script: The script for the classmate
            - roles: The roles for the classmate
    """

    def __init__(self, agent_name: str, task_name: str):
        self.agent_name = agent_name
        self.task_name = task_name
        self.agents_config = "config/agents.yaml"
        self.tasks_config = "config/tasks.yaml"        

    @agent
    def agent(self) -> Agent:
        return Agent(
            config=self.agents_config[self.agent_name],
        )
    @task
    def task(self) -> Task:
        return Task(
            config=self.tasks_config[self.task_name],
            agent=self.agent(),
        )
    
    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            # verbose=True,
        )