# core/task_formatter.py
from typing import Dict, List, Any

from core.stage_management.phase_config_loader import PhaseConfigLoader

class TaskFormatter:
    def __init__(self, phase_config_loader: PhaseConfigLoader): # Use string for forward reference
        self.phase_config_loader = phase_config_loader
        print(f"--- TaskFormatter: Initialized.")

    def format_task_status_for_prompt(self, phase_id_for_status: str, completed_tasks_map: Dict[str, List[str]]) -> str:
        phase_def_for_status = self.phase_config_loader.get_phase_data(phase_id_for_status)
        if not phase_def_for_status or 'tasks' not in phase_def_for_status:
            return "Không có nhiệm vụ nào được định nghĩa cho giai đoạn này."

        tasks_in_phase = phase_def_for_status.get('tasks', [])
        completed_ids_for_this_phase = []
        if isinstance(completed_tasks_map, dict):
            completed_ids_for_this_phase = [str(cid) for cid in completed_tasks_map.get(phase_id_for_status, [])]
        else:
            print(f"!!! WARN [TaskFormatter]: format_task_status_for_prompt received non-dict completed_tasks_map for phase {phase_id_for_status}. Defaulting to no tasks completed.")

        status_lines = []
        next_task_found = False
        if not tasks_in_phase:
            return "Giai đoạn này không có nhiệm vụ cụ thể nào được liệt kê."
            
        for task_dict in tasks_in_phase:
            task_id = task_dict.get('id')
            task_desc = task_dict.get('description')
            if task_id is None or task_desc is None: continue 

            is_done = str(task_id) in completed_ids_for_this_phase
            marker = "[X]" if is_done else "[ ]"
            next_marker = ""
            if not is_done and not next_task_found:
                next_marker = " <-- Nhiệm vụ tiếp theo cần tập trung"
                next_task_found = True
            status_lines.append(f"- {marker} ({task_id}) {task_desc}{next_marker}")

        if not status_lines: return "Không có nhiệm vụ nào cho giai đoạn này."
        return "\n".join(status_lines)

    def get_tasks_for_ui_display(self, phase_id: str, completed_tasks_map: Dict[str, List[str]]) -> List[Dict[str, Any]]:
        tasks_for_ui_display = []
        phase_data_from_config = self.phase_config_loader.get_phase_data(phase_id)
        defined_tasks = phase_data_from_config.get('tasks', [])
        
        completed_ids_for_current_phase = []
        if isinstance(completed_tasks_map, dict):
            completed_ids_for_current_phase = [str(tid) for tid in completed_tasks_map.get(phase_id, [])]

        for task_dict in defined_tasks:
            if isinstance(task_dict, dict) and 'id' in task_dict and 'description' in task_dict:
                task_id_str = str(task_dict['id'])
                tasks_for_ui_display.append({
                    "id": task_id_str,
                    "description": task_dict['description'],
                    "completed": task_id_str in completed_ids_for_current_phase
                })
            else:
                print(f"!!! WARN [TaskFormatter - Phase {phase_id}]: Corrupt task item in phase_data_from_config: {task_dict}")
        return tasks_for_ui_display