# core/stage_management/phase_config_loader.py
from typing import Dict, Any
from utils.loaders import load_phases_from_yaml

class PhaseConfigLoader:
    def __init__(self, phase_config_path: str):
        self.phases = self._load_and_process_phases_from_config(phase_config_path)
        if not self.phases:
            raise ValueError("Failed to load phase configurations.")
        print(f"--- PhaseConfigLoader: Initialized and phases loaded.")

    def _load_and_process_phases_from_config(self, filepath: str) -> Dict[str, Dict]:
        phases_cfg = load_phases_from_yaml(filepath)
        if not phases_cfg: return {}
        for phase_id, phase_data in phases_cfg.items():
            if 'tasks' in phase_data and isinstance(phase_data['tasks'], list):
                task_map = {}
                processed_tasks = []
                for task_idx, task_item in enumerate(phase_data['tasks']):
                    if isinstance(task_item, dict) and 'id' in task_item and 'description' in task_item:
                        task_map[task_item['id']] = task_item['description']
                        processed_tasks.append(task_item)
                    elif isinstance(task_item, str):
                        print(f"!!! WARN [PhaseConfigLoader]: Task in phase {phase_id} is a string, converting. Please update YAML. Task: {task_item}")
                        new_task_id = f"{phase_id}.{task_idx + 1}_auto"
                        task_map[new_task_id] = task_item
                        processed_tasks.append({'id': new_task_id, 'description': task_item})
                    else:
                        print(f"!!! WARN [PhaseConfigLoader]: Invalid task format in phase {phase_id}: {task_item}")
                phase_data['_task_map'] = task_map
                phase_data['tasks'] = processed_tasks
        return phases_cfg

    def get_phase_data(self, phase_id: str) -> Dict[str, Any]:
        return self.phases.get(phase_id, {})

    def get_all_phases(self) -> Dict[str, Dict[str, Any]]:
        return self.phases

    def get_task_map_for_phase(self, phase_id: str) -> Dict[str, str]:
        phase_data = self.get_phase_data(phase_id)
        return phase_data.get('_task_map', {})

    def get_defined_tasks_for_phase(self, phase_id: str) -> list:
        phase_data = self.get_phase_data(phase_id)
        return phase_data.get('tasks', [])