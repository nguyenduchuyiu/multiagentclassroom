#!/usr/bin/env python
from ast import literal_eval
import asyncio
from collections import deque
import json
import random
from pydantic import BaseModel
from crewai.flow import Flow, listen, start
from flow.crews.dialogueCrew import Participant, Evaluator, StageManager
from dotenv import load_dotenv
from flow.utils.helpers import (parse_json_response, parse_output, 
                     clean_response)
import time
import threading

from flow.utils.task_utils import track_task
from flow.utils.socket_utils import (send_message_via_socketio, 
                          send_agent_status_via_socketio, 
                          send_stage_update_via_socketio, 
                          send_system_status)
from flow.utils.helpers import save_to_log_file
# Import socketio from the main app module to use its sleep function
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
    completed_task_ids: list[str] = []
    talker: str = ""
    script: dict = {}
    current_stage_id: str = ""
    new_message: str = ""
    is_processing: bool = False  # Thêm trạng thái để kiểm tra xem luồng có đang xử lý không
    
class DialogueFlow(Flow[DialogueState]):
    def __init__(self, socketio, **kwargs):
        super().__init__()
        self.socketio = socketio
        self.state.conversation = kwargs["conversation"]
        save_to_log_file(f"Conversation: {self.state.conversation}\n", "test.txt")
        self.filename = kwargs["filename"]
        self.state.problem = kwargs["problem"]
        current_stage_description, completed_task_ids, current_stage_id = track_task(kwargs["stage_state"], 
                                                          kwargs["current_stage_id"],
                                                          kwargs["script"])
        self.state.current_stage_description = current_stage_description
        self.state.completed_task_ids = completed_task_ids
        self.state.current_stage_id = current_stage_id
        self.state.participants = kwargs["participants"]
        self.state.script = kwargs["script"]
        self.thinker_list = [Participant(agent_name, "think") for agent_name in self.state.participants]    
        self.talker_list = [Participant(agent_name, "talk") for agent_name in self.state.participants]
        self.state.turn_number = kwargs["turn_number"]
        self.state.inner_thought = kwargs["inner_thought"]
        self.session_id = kwargs.get("session_id", "")  # Lưu session_id để gửi thông báo đến đúng phòng
        self.user_name = kwargs.get("user_name", "User")
        self.roles = kwargs.get("roles")
        self.processing_lock = threading.Lock()  # Lock để đảm bảo chỉ có một luồng xử lý cùng lúc
        self._is_cancelled = False # Thêm cờ hủy
        
        if self.state.turn_number == 0:
            with open(self.filename, "w") as f:  # Use append mode to accumulate turns
                script = "\n\n".join([f"{k}: {v}" for key, value in self.state.script.items() for k, v in value.items()])
                f.write(f'Script:\n{script}\n\n')
                f.write(f"Conversation:\n{self.state.conversation}\n")
            
        # print("--- DIALOGUE FLOW INITIALIZED WITH ---")
        # print(f"Conversation: {self.state.conversation}")
        # print(f"Log File: {self.filename}")
        # print(f"Problem: {self.state.problem}")
        # print(f"Current Stage ID: {self.state.current_stage_id}")
        # print(f"Current Stage Description: {self.state.current_stage_description}")
        # print(f"Participants: {self.state.participants}")
        # print(f"Script: {self.state.script}")
        # print(f"Turn Number: {self.state.turn_number}")
        # print(f"Session ID: {self.session_id}")
        # print(f"User Name: {self.user_name}")
        # print(f"Roles: {self.roles}")
        # print("--- END OF DIALOGUE FLOW INITIALIZATION ---")
        
    def cancel(self):
        """Sets the cancellation flag."""
        print(f"--- DIALOGUE FLOW [{self.session_id}]: Cancellation requested.")
        self._is_cancelled = True
        # Có thể thêm logic để cố gắng dừng các tác vụ con nếu cần (phức tạp hơn)

    @start()    
    def manage_stage(self):
        if self._is_cancelled: # Kiểm tra cờ hủy
            print(f"--- DIALOGUE FLOW [{self.session_id}]: manage_stage cancelled.")
            return # Dừng xử lý

        print("Managing stage")
        if self.session_id:
            send_system_status("Đang cập nhật trạng thái nhiệm vụ...", self.session_id)
            
        stage_manager = StageManager()
        stage_manager_result = stage_manager.crew().kickoff(inputs={
            "conversation": self.state.conversation,
            "problem": self.state.problem,
            "current_stage_description": self.state.current_stage_description
        })
        
        stage_state = parse_json_response(clean_response(stage_manager_result.raw))
        if stage_state is not None:
            self.state.stage_state = stage_state
        else:
            print("Warning: Stage state is None")
            
        current_stage_description, completed_task_ids, current_stage_id = track_task(self.state.stage_state, 
                                                          self.state.current_stage_id, 
                                                          self.state.script)

        self.state.current_stage_description = current_stage_description
        self.state.completed_task_ids = completed_task_ids
        if int(current_stage_id) != int(self.state.current_stage_id):
            self.state.current_stage_id = current_stage_id
            save_to_log_file(f"Stage changed to {current_stage_id}\n", self.filename)
        
        if self.session_id:
            send_stage_update_via_socketio({
                'current_stage_id': self.state.current_stage_id,
                'completed_task_ids': self.state.completed_task_ids
            }, self.session_id)

    @listen(manage_stage)
    async def generate_inner_thought(self):
        if self._is_cancelled: # Kiểm tra cờ hủy
            print(f"--- DIALOGUE FLOW [{self.session_id}]: generate_inner_thought cancelled.")
            return # Dừng xử lý
        
        # Cập nhật trạng thái các agent đang suy nghĩ
        if self.session_id:
            for agent in self.thinker_list:
                send_agent_status_via_socketio(agent.agent_name, "thinking", self.session_id)
        
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
        if self._is_cancelled: # Kiểm tra cờ hủy
            print(f"--- DIALOGUE FLOW [{self.session_id}]: evaluate_inner_thought cancelled.")
            return # Dừng xử lý

        evaluator = Evaluator()
        # Take the latest list of inner thoughts (for this turn)
        latest_inner_thought_list = self.state.inner_thought[-1]
        evaluation = evaluator.crew().kickoff(inputs={
            "problem": self.state.problem,
            "current_stage_description": self.state.current_stage_description,
            "conversation": self.state.conversation,
            "thoughts": json.dumps(latest_inner_thought_list), # evaluate all agents' thoughts in this turn
            "roles": self.roles
        })
        self.state.evaluation = parse_json_response(clean_response(evaluation.raw)) # [{}]
        
        # Done thinking, set all agents to idle
        for participant in self.state.participants:
            send_agent_status_via_socketio(participant, "idle", self.session_id)
        
    @listen(evaluate_inner_thought)
    def generate_speech(self):
        if self._is_cancelled: # Kiểm tra cờ hủy
            print(f"--- DIALOGUE FLOW [{self.session_id}]: generate_speech cancelled.")
            return # Dừng xử lý

        try:
            # select_talker giờ đây chỉ ném ra RuntimeError hoặc trả về None
            self.state.talker = self.select_talker(self.state.evaluation)

            if self.state.talker is None:
                # Trường hợp 1: Không có agent nào chọn 'speak' (tất cả chọn nghe)
                if self.session_id:
                    send_system_status("Các agent đang lắng nghe. Chưa có ai muốn nói.", self.session_id)
                # Đặt trạng thái speech và talker để đảm bảo các bước sau không xử lý nhầm
                self.state.speech = ""

            # Trường hợp 2: Đã chọn được người nói thành công
            # Lệnh print đã được chuyển vào select_talker

            # Chỉ người nói đang gõ
            if self.session_id:
                send_agent_status_via_socketio(self.state.talker, "typing", self.session_id)

            agent = next(talker for talker in self.talker_list if talker.agent_name == self.state.talker)

            speech = agent.crew().kickoff(inputs={
                "problem": self.state.problem,
                "current_stage_description": self.state.current_stage_description,
                "conversation": self.state.conversation,
                "participants": self.state.participants,
                "thought": next((item["inner_thought"] for item in self.state.inner_thought[-1] if item["agent"] == self.state.talker), "")
            })
            self.state.speech = parse_output(speech.raw, "spoken_message")

            self.state.turn_number += 1 # Tăng số lượt khi agent nói xong

            self.state.new_message = (
                f"TIME={time.time()} | "
                f"CON#{self.state.turn_number} | "
                f"SENDER={self.state.talker} | "
                f"TEXT={self.state.speech}\n"
            )


        except Exception as e:
            # Xử lý các lỗi không mong muốn khác trong quá trình tạo lời nói (không phải từ select_talker)
            print(f"--- DIALOGUE FLOW [{self.session_id}]: Unexpected error during speech generation (outside of talker selection): {e}")
            if self.session_id:
                send_system_status(f"Đã xảy ra lỗi không mong muốn khi tạo lời nói: {e}", self.session_id)
            self.state.speech = ""
            self.state.talker = None
            return # Thoát khỏi hàm

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
            f.write(f'''Turn: {self.state.turn_number}.
================================================= 
Stage state:\n {stage_state}

Inner thoughts:\n{inner_thoughts}

Evaluation:\n{evaluation}
=================================================
''')
            if self.state.talker:
                f.write(self.state.new_message)
            else:
                f.write(f"TIME={time.time()} | CON#{self.state.turn_number} | SENDER=System | TEXT=No agent chose to speak.\n")
            f.write("\n")
        
        # Set talker to idle
        if self.session_id and self.state.talker: # Only set status if a talker was selected
            send_agent_status_via_socketio(self.state.talker, "idle", self.session_id)
        
    def process_new_message(self, sender_name, text):
        """
        Xử lý tin nhắn mới từ client và kích hoạt luồng xử lý nếu không có luồng nào đang chạy.

        Args:
            sender_name (str): Tên người gửi
            text (str): Nội dung tin nhắn
        """
        # Kiểm tra cờ hủy ngay khi nhận tin nhắn mới
        if self._is_cancelled:
            print(f"--- DIALOGUE FLOW [{self.session_id}]: Received message '{text}' but flow is cancelled. Ignoring.")
            if self.session_id:
                 send_system_status("Phiên trò chuyện đã kết thúc hoặc đang được đóng. Vui lòng tạo phiên mới.", self.session_id)
            return # Bỏ qua tin nhắn nếu flow đã bị hủy

        new_message_str = (
            f"TIME={time.time()} | "
            f"CON#{self.state.turn_number} | "
            f"SENDER={sender_name} | "
            f"TEXT={text}\n"
        )
        
        # Save the new message to the log file if the sender is not a participant (means it's the user)
        # and update turn number. This happens immediately.
        if sender_name not in self.state.participants:
            self.state.turn_number += 1
            # Update the new message string with the new turn number
            new_message_str = (
                f"TIME={time.time()} | "
                f"CON#{self.state.turn_number} | "
                f"SENDER={sender_name} | "
                f"TEXT={text}\n"
            )
            save_to_log_file(f"Turn: {self.state.turn_number}.\n{new_message_str}\n", 
                                  self.filename)

        # Append to conversation history immediately
        self.state.conversation += new_message_str

        should_start_flow = False

        # Try to acquire the processing lock
        lock_acquired = self.processing_lock.acquire(blocking=False)

        if lock_acquired:
            try:
                # If lock acquired, check if a flow is already running
                if not self.state.is_processing:
                    print(f"Processing message from {sender_name}: {text}")
                    self.state.is_processing = True
                    self.state.new_message = new_message_str # Store the message that triggered this turn
                    should_start_flow = True # Flag to indicate kickoff needed after lock release
                else:
                    # Lock acquired, but a flow is already running
                    print("A message processing flow is already running. Adding new message to conversation and logging.")
            finally:
                self.processing_lock.release()
        else:
            # Lock not acquired, another thread is processing
            print("Another thread is already processing a message. Adding new message to conversation and logging.")

        # If we are not starting a new flow, handle the busy state
        if not should_start_flow:
            if self.session_id:
                send_system_status("Hệ thống đang xử lý tin nhắn trước đó. Vui lòng đợi.", self.session_id)
        else:
            # If we are starting a new flow, kickoff outside the lock
            try:
                # Kiểm tra cờ hủy lần nữa trước khi kickoff
                if self._is_cancelled:
                     print(f"--- DIALOGUE FLOW [{self.session_id}]: Flow cancelled before kickoff. Aborting.")
                     self.state.is_processing = False
                     if self.session_id:
                          send_system_status("Phiên trò chuyện đã kết thúc hoặc đang được đóng. Vui lòng tạo phiên mới.", self.session_id)
                     return

                # Add the non-blocking sleep here before kicking off the main flow
                print(f"--- DIALOGUE FLOW [{self.session_id}]: Waiting for 10 seconds before starting flow...")
                self.socketio.sleep(10) # Use socketio.sleep for non-blocking delay
                print(f"--- DIALOGUE FLOW [{self.session_id}]: Starting flow after delay.")

                self.kickoff()
                self.state.is_processing = False

                # Send the agent's message after the flow completes, if a talker was selected
                if self.session_id and not self._is_cancelled and self.state.talker:
                    send_message_via_socketio({
                        'source': 'agent',
                        'content': {
                            'text': self.state.speech,
                            'sender_name': self.state.talker
                        }
                    }, self.session_id)
            except Exception as e:
                print(f"Error kicking off flow: {e}")
                # Đảm bảo reset trạng thái xử lý và giải phóng lock nếu có lỗi
                if self.processing_lock.locked():
                     self.processing_lock.release()
                self.state.is_processing = False
                if self.session_id:
                     send_system_status(f"Đã xảy ra lỗi trong quá trình xử lý: {e}", self.session_id)

    def export_session_data(self):
        """
        Export the session data needed to store in the database.
        """
        session_data = {
            "session_id": self.session_id,
            "problem": self.state.problem,
            "script": self.state.script,
            "roles": self.roles,
            "current_stage_id": self.state.current_stage_id,
            "conversation": self.state.conversation,
            "log_file": self.filename,
            "stage_state": self.state.stage_state if self.state.stage_state 
                                                    else 
                                                    {"completed_task_ids": [],
                                                     "signal": "1"},
            "inner_thought": list(self.state.inner_thought) if self.state.inner_thought else [],  # Convert deque to list
            "turn_number": self.state.turn_number,
            "user_name": self.user_name
        }
        return session_data
    
    def select_talker(self, evaluation_results, lambda_weight=0.5):
        '''
        Select the talker based on the evaluation results.
        Only agents with action 'speak' and valid numeric scores are considered.
        The selection is based on a weighted average of internal and external scores.

        Returns:
            str: The name of the selected talker.
            None: If no agent chose to 'speak'.
        Raises:
            RuntimeError: If any error occurs during the selection process (invalid format, invalid data, etc.).
        '''
        try:
            potential_talkers_details = []

            for result in evaluation_results:
                if result.get('action') == 'speak':
                    agent_name = result.get('name')
                    internal_score = result.get('internal_score')
                    external_score = result.get('external_score')

                    final_score_val = ((1 - lambda_weight) * internal_score +
                                       lambda_weight * external_score +
                                       random.uniform(-0.01, 0.01))

                    potential_talkers_details.append({
                        "name": agent_name,
                        "final_score": final_score_val
                    })

            if not potential_talkers_details:
                print(f"--- DIALOGUE FLOW [{self.session_id}]: No agent chose to speak or had valid scores.")
                return None

            potential_talkers_details.sort(key=lambda x: x["final_score"], reverse=True)
            selected_agent_name = potential_talkers_details[0]["name"]
            print(f"--- DIALOGUE FLOW [{self.session_id}]: Selected talker: {selected_agent_name}")
            return selected_agent_name

        except Exception as e:
            print(f"--- DIALOGUE FLOW [{self.session_id}]: An unexpected error occurred in select_talker: {e}")
            raise RuntimeError(f"Error selecting talker: {e}") from e # Ném RuntimeError và giữ lại thông tin lỗi gốc
        
