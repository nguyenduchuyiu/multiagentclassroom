#!/usr/bin/env python
from ast import literal_eval
import asyncio
from collections import deque
import json
from pydantic import BaseModel
from crewai.flow import Flow, listen, start
from flow.crews.dialogueCrew import Participant, Evaluator, StageManager
from dotenv import load_dotenv
from flow.utils.helpers import (parse_json_response, parse_output, 
                     clean_response, select_talker)
import time
from flask_socketio import emit
import os # Đảm bảo đã import os
import re

from flow.utils.task_tracker import track_task
load_dotenv()

class DialogueState(BaseModel):
    conversation: str = ""
    inner_thought: deque[list[dict]] = deque(maxlen=5)
    participants: list[str] = []
    evaluation: list[dict] = [] 
    speech: str = ""
    stage_state: dict = {}
    turn_number: int = 0
    problem: str = ""
    current_stage_description: str = ""
    talker: str = ""
    script: dict = {}
    current_stage_id: str = ""
    new_message: str = ""
    
class DialogueFlow(Flow[DialogueState]):
    def __init__(self, **kwargs):
        super().__init__()
        self.state.conversation = kwargs["conversation"]
        self.filename = kwargs["filename"]
        self.state.problem = kwargs["problem"]
        self.state.current_stage_id = kwargs["current_stage_id"]
        self.state.current_stage_description = track_task(kwargs["stage_state"], 
                                                          kwargs["current_stage_id"],
                                                          kwargs["script"])
        self.state.participants = kwargs["participants"]
        self.state.script = kwargs["script"]
        self.thinker_list = [Participant(agent_name, "think") for agent_name in self.state.participants]    
        self.talker_list = [Participant(agent_name, "talk") for agent_name in self.state.participants]
        self.state.turn_number = len(self.state.conversation.split("CON#")) - 1
        self.state.inner_thought = kwargs["inner_thought"]
        
        print("--- DIALOGUE FLOW INITIALIZED WITH ---")
        print(f"Conversation: {self.state.conversation}")
        print(f"Log File: {self.filename}")
        print(f"Problem: {self.state.problem}")
        print(f"Current Stage ID: {self.state.current_stage_id}")
        print(f"Current Stage Description: {self.state.current_stage_description}")
        print(f"Participants: {self.state.participants}")
        print(f"Script: {self.state.script}")
        print(f"Turn Number: {self.state.turn_number}")
        print("--- END OF DIALOGUE FLOW INITIALIZATION ---")
        
    @start()
    def generate_conversation(self):
        print(f"Turn {self.state.turn_number}")
        print(f"Processing message: {self.state.new_message}")
        self.state.conversation += self.state.new_message

        
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
                "participants": self.state.participants,
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
            "participants": self.state.participants,
            "thought": next((item["inner_thought"] for item in self.state.inner_thought[-1] if item["agent"] == self.state.talker), "")
        })
        self.state.speech = parse_output(speech.raw, "spoken_message")

        new_message = (
            f"TIME={time.time()} | "
            f"CON#{self.state.turn_number} | "
            f"SENDER={self.state.talker} | "
            f"TEXT={self.state.speech}\n"
        )
        
        return new_message
        

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

    def process_new_message(self, sender_name, text):
        print(f"Processing message from {sender_name}: {text}")
        self.state.turn_number += 1
        self.state.new_message = (
            f"TIME={time.time()} | "
            f"CON#{self.state.turn_number} | "
            f"SENDER={sender_name} | "
            f"TEXT={text}\n"
        )
        
        # Kick off the flow with the new message
        response = self.kickoff()
        
        # The generate_speech method returns a new message that we'll use to send an agent response
        if response:
            # Extract agent name and text from the response
            pattern = r"TIME=([0-9.]+) \| CON#(\d+) \| SENDER=([^|]+) \| TEXT=(.+)"
            match = re.match(pattern, response)
            if match:
                _, _, agent_name, agent_text = match.groups()
                agent_name = agent_name.strip()
                agent_text = agent_text.strip()
                
                # Use socketio to emit the agent message
                emit('new_message', {
                    'source': 'agent',
                    'content': {
                        'text': agent_text,
                        'sender_name': agent_name
                    },
                    'timestamp': int(time.time() * 1000)
                }, namespace='/')

    def send_message_via_socketio(self, message_data, session_id):
        """
        Send a message via Socket.IO to clients in the session room.
        
        Args:
            message_data (dict): The message data to send
            session_id (str): The session ID to send the message to
        """
        # Emit the message to the specific room (session)
        emit('new_message', {
            'source': message_data['source'],
            'content': message_data['content'],
            'timestamp': int(time.time() * 1000)
        }, room=session_id, namespace='/')

    def send_agent_status_via_socketio(self, agent_name, status, session_id):
        """
        Send an agent status update via Socket.IO to clients in the session room.
        
        Args:
            agent_name (str): The name of the agent
            status (str): The status of the agent ('idle', 'thinking', 'typing')
            session_id (str): The session ID to send the status update to
        """
        status_data = {
            'source': 'system',
            'content': {
                'agent_name': agent_name,
                'status': status
            },
            'timestamp': int(time.time() * 1000)
        }
        
        emit('agent_status', status_data, room=session_id, namespace='/')

    def send_stage_update_via_socketio(self, stage_data, session_id):
        """
        Send a stage update via Socket.IO to clients in the session room.
        
        Args:
            stage_data (dict): The stage data to send
            session_id (str): The session ID to send the stage update to
        """
        update_data = {
            'source': 'system',
            'content': stage_data,
            'timestamp': int(time.time() * 1000)
        }
        
        emit('stage_update', update_data, room=session_id, namespace='/')






