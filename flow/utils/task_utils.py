def track_task(stage_state: dict, current_stage_id: str, script: dict):
    '''
    Track the task for the current stage.
    Return the current stage description.
    '''
    print("stage_state ", stage_state)
    completed_task_ids = stage_state["completed_task_ids"]
    signal = stage_state["signal"]
    all_task_ids = [task["id"] for task in script[current_stage_id]["tasks"]]
    max_number_of_stage = len(script.keys())
    uncompleted_task_ids = [task_id for task_id in all_task_ids if task_id not in completed_task_ids]
    next_stage_id = str(int(current_stage_id) + 1)
    
    # signal = 3 means the move to the next stage
    if len(uncompleted_task_ids) == 0 and signal[0] == "3" and int(next_stage_id) <= max_number_of_stage:
        return initialize_task(script, next_stage_id), completed_task_ids, next_stage_id
    
    else:
        task_status = []
        next_task_id = None
        for i, task_id in enumerate(all_task_ids):
            if task_id in completed_task_ids:
                task_status.append(f'''
                [X] [{task_id}] {script[current_stage_id]["tasks"][i]["description"]}
                ''')
            else:
                if next_task_id is None:
                    next_task_id = task_id
                    task_status.append(f'''
                [!] [{task_id}] {script[current_stage_id]["tasks"][i]["description"]}
                    ''')
                else:
                    task_status.append(f'''
                [] [{task_id}] {script[current_stage_id]["tasks"][i]["description"]}
                    ''')
        task_status = "\n".join(task_status)
        current_stage_description = f'''
        Name: {script[current_stage_id]["name"]}
        Description: {script[current_stage_id]["description"]}
        Đây là các nhiệm vụ cần thực hiện, [X] là task đã làm xong, [] là task chưa làm, [!] là task tiếp theo cần tập trung:
        Tasks:
        {task_status}
        '''
        return current_stage_description, completed_task_ids, current_stage_id

def initialize_task(script: dict, current_stage_id: str):
    '''
    Initialize the task description for the current stage.
    Return the current stage description.
    '''
    current_stage_description = f'''
    Name: {script[current_stage_id]["name"]}
    Description: {script[current_stage_id]["description"]}
    Đây là các nhiệm vụ cần thực hiện, [X] là task đã làm xong, [] là task chưa làm, [!] là task tiếp theo cần tập trung:
    Tasks:
    '''
    tasks = script[current_stage_id]["tasks"]
    current_stage_description += f'''
        [!] [{tasks[0]["id"]}] {tasks[0]["description"]}
    '''
    for task in tasks[1:]:
        current_stage_description += f'''
        [] [{task["id"]}] {task["description"]}
        '''
    return current_stage_description

# print(initialize_task(load_yaml("macls/src/macls/crews/classmate_crew/config/base_script.yaml"), "2"))
# stage_state = {"completed_task_ids": ["2.1", "2.2"], "signal": "3"}
# print(track_task(stage_state, "2", load_yaml("macls/src/macls/crews/classmate_crew/config/base_script.yaml")))
