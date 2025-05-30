import os
from pydantic import BaseModel
from crewai.flow import Flow, start
from flow.crews.scriptGenerationCrew import ScriptWriter
from dotenv import load_dotenv
from flow.utils.helpers import parse_yaml, save_yaml

load_dotenv()


class ScriptGenerationState(BaseModel):
    script: dict = {}
    roles: dict = {}

class ScriptGenerationFlow(Flow[ScriptGenerationState]):
    def __init__(self, **kwargs):
        super().__init__()
        self.problem = kwargs["problem"]
        self.solution = kwargs["solution"]
        self.keywords = kwargs["keywords"]

    @start()
    def generate_script_and_roles(self):
        script_writer = ScriptWriter(agent_name="ScriptWriter", task_name="write_script")
        roles_writer = ScriptWriter(agent_name="RolesWriter", task_name="write_roles")
        script = script_writer.crew().kickoff(inputs={
            "problem": self.problem,
            "solution": self.solution,
            "keywords": self.keywords
        })
        self.state.script = script.raw.replace("```yaml", "").replace("```", "")
        
        roles = roles_writer.crew().kickoff(inputs={
            "problem": self.problem,
            "solution": self.solution,
            "keywords": self.keywords,
            "script": self.state.script
        })
        self.state.roles = roles.raw.replace("```yaml", "").replace("```", "")
        
        return self.state.script, self.state.roles
    
def generate_script_and_roles(folder_path: str, **kwargs: dict) -> tuple[dict, dict]:
    '''
    Generate script and roles for the given problem and solution and save them to the given folder
    Input:
        folder_path: The path to the folder where the script and roles will be saved
        kwargs: The keyword arguments for the ScriptGenerationFlow 
            - problem: The problem for the script generation
            - solution: The solution for the script generation
            - keywords: The keywords for the script generation
    Output:
        script: The script for the given problem and solution
        roles: The roles for the given problem and solution
    '''
    dynamic_script_path = f"{folder_path}/dynamic_script.yaml"
    dynamic_participants_path = f"{folder_path}/dynamic_participants.yaml"
    scriptFlow = ScriptGenerationFlow(**kwargs)
    script, roles = scriptFlow.kickoff()
    script = parse_yaml(script)
    roles = parse_yaml(roles)
    save_yaml(dynamic_script_path, script)
    save_yaml(dynamic_participants_path, roles)

    return script, roles