#!/usr/bin/env python
from ast import literal_eval
import asyncio
from collections import deque
import json
from pydantic import BaseModel
from crewai.flow import Flow, listen, start
from flow.crews.dialogueCrew import Participant, Evaluator, ScriptWriter, StageManager
from dotenv import load_dotenv
from flow.utils.helpers import (create_agent_config, dummy_llm_call, 
                     load_yaml, parse_json_response, parse_output, 
                     clean_response, parse_yaml, save_yaml, select_talker)
import uuid

from flow.utils.task_tracker import initialize_task, track_task
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



class DialogueState(BaseModel):
    conversation: str = ""
    inner_thought: deque[list[dict]] = deque(maxlen=5)
    classmate: list[str] = []
    evaluation: list[dict] = [] 
    speech: str = ""
    stage_state: dict = {}
    turn_number: int = 0
    problem: str = ""
    current_stage_description: str = ""
    talker: str = ""
    script: dict = {}
    current_stage_id: str = ""
    
class DialogueFlow(Flow[DialogueState]):
    def __init__(self, **kwargs):
        super().__init__()
        file_uuid = uuid.uuid4()
        self.state.conversation = f'''CONV.0. Chào mừng các bạn đến với nhóm chat. Bài toán chúng ta cần thảo luận là {problem}\n'''
        self.filename = f"conversation_{file_uuid}.txt"
        self.state.problem = kwargs["problem"]
        self.state.current_stage_id = "1"
        self.state.current_stage_description = initialize_task(kwargs["script"], self.state.current_stage_id)
        self.state.classmate = kwargs["classmate"]
        self.state.script = kwargs["script"]
        self.thinker_list = [Participant(agent_name, "think") for agent_name in self.state.classmate]    
        self.talker_list = [Participant(agent_name, "talk") for agent_name in self.state.classmate]
        
    @start()
    def generate_conversation(self):
        self.state.turn_number += 1
        print(f"Turn {self.state.turn_number}")

    @listen(generate_conversation)
    def manage_stage(self):
        print("Managing stage")
        stage_manager = StageManager()
        stage_manager_result = stage_manager.crew().kickoff(inputs={
            "conversation": self.state.conversation,
            "problem": self.state.problem,
            "current_stage_description": self.state.current_stage_description
        })
        
        self.state.stage_state = parse_json_response(clean_response(stage_manager_result.raw))
        self.state.current_stage_description = track_task(self.state.stage_state, 
                                                          self.state.current_stage_id, 
                                                          self.state.script)


    @listen(manage_stage)
    async def generate_inner_thought(self):
        print("Generating inner thought")
        # Tạo danh sách các coroutine
        tasks = [
            agent.crew().kickoff_async(inputs={
                "problem": self.state.problem,
                "current_stage_description": self.state.current_stage_description,
                "conversation": self.state.conversation,
                "classmate": [name for name in self.state.classmate if name != agent.agent_name],
                "previous_thoughts": [
                    d["inner_thought"]
                    for turn in self.state.inner_thought
                    for d in turn
                    if d["agent"] == agent.agent_name
                ]
            })
            for agent in self.thinker_list
        ]

        # Chờ tất cả coroutine hoàn thành
        results = await asyncio.gather(*tasks)

        # Lưu kết quả vào self.state.inner_thought dưới dạng list các dict (one per agent)
        inner_thought_list = [
            {
                "agent": agent.agent_name,
                "inner_thought": clean_response(result.raw)
            }
            for agent, result in zip(self.thinker_list, results)
        ]
        self.state.inner_thought.append(inner_thought_list)  # Append the list for this turn


    @listen(generate_inner_thought)
    async def evaluate_inner_thought(self):
        print("Evaluating inner thought")
        evaluator = Evaluator()
        # Take the latest list of inner thoughts (for this turn)
        latest_inner_thought_list = self.state.inner_thought[-1]
        evaluation = evaluator.crew().kickoff(inputs={
            "problem": self.state.problem,
            "current_stage_description": self.state.current_stage_description,
            "conversation": self.state.conversation,
            "thoughts": json.dumps(latest_inner_thought_list) # evaluate all agents' thoughts in this turn
        })
        self.state.evaluation = literal_eval(clean_response(evaluation.raw)) # [{}]
        


    @listen(evaluate_inner_thought)
    def generate_speech(self):
        print("Generating speech")
        self.state.talker = select_talker(self.state.evaluation)
        if self.state.talker is None:
            print("Talker is None, let Bob handle :).")
            self.state.talker = "Bob"
            
        agent = next(talker for talker in self.talker_list if talker.agent_name == self.state.talker)

        speech = agent.crew().kickoff(inputs={
            "problem": self.state.problem,
            "current_stage_description": self.state.current_stage_description,
            "conversation": self.state.conversation,
            "classmate": [name for name in self.state.classmate if name != self.state.talker],
            "thought": next((item["inner_thought"] for item in self.state.inner_thought[-1] if item["agent"] == self.state.talker), "")
        })
        self.state.speech = parse_output(speech.raw, "spoken_message")
        self.state.conversation += f"CON#{self.state.turn_number}. {self.state.talker}: {self.state.speech}\n"


    @listen(generate_speech)
    def save_final_answers(self):
        stage_state = "\n".join([f"{key}: {value}" for key, value in self.state.stage_state.items()])
        # Find the inner thought for the talker in the latest turn
        latest_inner_thought_list = self.state.inner_thought[-1] if self.state.inner_thought else []
        inner_thoughts = "\n".join([f"{item['agent']}: {item['inner_thought']}" for item in latest_inner_thought_list])
        # Get the evaluation for this turn
        evaluation = "\n\n".join([
            "\n".join([f"{key}: {value}" for key, value in item.items()])
            for item in self.state.evaluation
        ])
        with open(self.filename, "a") as f:  # Use append mode to accumulate turns
            if self.state.turn_number == 1:
                script = "\n\n".join([f"{k}: {v}" for key, value in self.state.script.items() for k, v in value.items()])
                f.write(f'Script:\n{script}\n\n')
                
            f.write(f'''Turn: {self.state.turn_number}.
================================================= 
Stage state:\n {stage_state}

Inner thoughts:\n{inner_thoughts}

Evaluation:\n{evaluation}
=================================================
''')
            f.write(f"{self.state.talker}: {self.state.speech}\n")
            f.write("\n")



async def kickoff_async_loop(n=3, **kwargs):
    
    dialogue_flow = DialogueFlow(**kwargs)  # Create a single instance to keep state
    for i in range(n):
        await dialogue_flow.kickoff_async()  # This will keep updating the same state



if __name__ == "__main__":
    
    folder_path = "crew/classmate_crew/config"
    base_participants_path = f"{folder_path}/base_participants.yaml"
    meta_agents_path = f"{folder_path}/meta_agents.yaml"
    dynamic_participants_path = f"{folder_path}/dynamic_participants.yaml"
    output_path = f"{folder_path}/agents.yaml"
    base_script_path = f"{folder_path}/base_script.yaml"
    dynamic_script_path = f"{folder_path}/dynamic_script.yaml"
    problem_path = f"{folder_path}/problems.yaml"
    
    problems = load_yaml(problem_path)
    problem = problems["1"]["problem"]
    solution = problems["1"]["solution"]

    keywords = [
        "rap", "MC", "DJ", "breakdance", "graffiti", "beatbox", "freestyle", "flow", "bars", "cypher",
        "turntable", "sampling", "boom bap", "trap", "crew", "battle", "scratch", "b-boy", "b-girl",
        "old school", "new school", "streetwear", "mic", "hook", "verse", "chorus", "producer", "remix",
        "beat", "rhymes", "diss", "mixtape", "underground", "mainstream", "block party", "bling", "swagger"
    ]
    kwargs = {
        "problem": problem,
        "solution": solution,
        "keywords": keywords,
        "classmate": None,
        "script": load_yaml(base_script_path),
        "roles": None,
    }
    
    # If script and classmate are provided, run flow with the provided script and classmate.
    if kwargs["script"] and kwargs["classmate"]:
        pass
    else:
        # If no script is provided, generate dynamic script and participants
        if kwargs["script"] is None:
            current_participants_path = dynamic_participants_path

            script_flow = ScriptGenerationFlow(**kwargs)
            script, roles = script_flow.kickoff()
        
            save_yaml(dynamic_script_path, script)
            save_yaml(dynamic_participants_path, roles)
                
            kwargs["script"] = parse_yaml(script)
            kwargs["roles"] = parse_yaml(roles)
        else:
            # If script is provided but no classmate is provided, use the base participants
            current_participants_path = base_participants_path

        
        create_agent_config(
            current_participants_path,
            meta_agents_path,
            output_path
        )

        roles_config = load_yaml(current_participants_path)
        kwargs["classmate"] = list(roles_config.keys())
        
    print(kwargs["classmate"])
    
    asyncio.run(kickoff_async_loop(n=5, **kwargs))
    # plot()
