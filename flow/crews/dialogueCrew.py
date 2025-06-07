from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from dotenv import load_dotenv

load_dotenv()
    
@CrewBase
class Participant:
    """Participant Crew"""

    def __init__(self, agent_name, task_name):
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

@CrewBase
class Evaluator():
    """Evaluator Crew"""
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"
    
    @agent
    def evaluator(self) -> Agent:
        return Agent(
            config=self.agents_config["Evaluator"],
        )

    @task
    def evaluate(self) -> Task:
        return Task(
            config=self.tasks_config["evaluate"],
            agent=self.evaluator(),
        )
    
    @crew
    def crew(self) -> Crew:
        """Creates the Evaluator Crew"""

        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            # verbose=True,
        )


@CrewBase
class StageManager():
    """Stage Manager Crew"""
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"
    
    @agent
    def stage_manager(self) -> Agent:
        return Agent(
            config=self.agents_config["StageManager"],
        )
    
    @task
    def manage_stage(self) -> Task:
        return Task(
            config=self.tasks_config["manage_stage"],
            agent=self.stage_manager(),
        )
    
    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            # verbose=True,
        )