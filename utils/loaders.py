# utils/loaders.py
import traceback
import yaml
import uuid
from typing import Dict, List, Optional
from core.persona import Persona # Import the dataclass

def load_personas_from_yaml(filepath: str) -> Dict[str, Persona]:
    """Loads agent personas from a YAML file."""
    personas = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            agents_cfg = yaml.safe_load(f)

        if not isinstance(agents_cfg, dict):
             print(f"!!! ERROR [Loader]: Invalid YAML format in {filepath}. Expected a dictionary.")
             return {}

        for agent_name, props in agents_cfg.items():
            if not isinstance(props, dict):
                 print(f"!!! WARN [Loader]: Skipping invalid entry for '{agent_name}' in {filepath}.")
                 continue

            agent_id = str(uuid.uuid4())

            persona = Persona(
                agent_id=agent_id,
                name=agent_name,
                role=props.get('role', ''),
                goal=props.get('goal', ''),
                backstory=props.get('backstory', ''),
                # <<< ASSIGN the tasks value >>>
                tasks=props.get('tasks', ''), # Get the tasks string from YAML
                personality_traits=props.get('personality_traits', []),
                model=props.get('model', 'gemini-2.0-flash'),
                tools=props.get('tools', [])
            )
            personas[agent_id] = persona
            print(f"--- LOADER: Loaded persona for {agent_name} with ID {agent_id}")

    except FileNotFoundError:
        print(f"!!! ERROR [Loader]: Persona configuration file not found: {filepath}")
    except yaml.YAMLError as e:
        print(f"!!! ERROR [Loader]: Error parsing YAML file {filepath}: {e}")
    except Exception as e:
        print(f"!!! ERROR [Loader]: Unexpected error loading personas from {filepath}: {e}")

    return personas


def load_phases_from_yaml(filepath: str) -> Dict[str, Dict]:
    """Loads conversation phase definitions from a YAML file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            phases_cfg = yaml.safe_load(f)
        if not isinstance(phases_cfg, dict):
             print(f"!!! ERROR [Loader]: Invalid YAML format in {filepath}. Expected a dictionary for phases.")
             return {}
        # TODO: Add validation for phase structure if needed
        print(f"--- LOADER: Loaded {len(phases_cfg)} phases from {filepath}")
        return phases_cfg
    except FileNotFoundError:
        print(f"!!! WARN [Loader]: Phase configuration file not found: {filepath}. Using defaults.")
        return {} # Return empty dict to signal using defaults
    except yaml.YAMLError as e:
        print(f"!!! ERROR [Loader]: Error parsing YAML file {filepath}: {e}")
        return {}
    except Exception as e:
        print(f"!!! ERROR [Loader]: Unexpected error loading phases from {filepath}: {e}")
        return {}
    
def load_problem_context(filepath: str) -> Optional[Dict[str, Dict[str, str]]]:
    """Loads multiple problems and their solutions from a YAML file.
    Expects a YAML structure like:
    "1":
      problem: "Problem description for 1..."
      solution: "Solution for 1..."
    "2":
      problem: "Problem description for 2..."
      solution: "Solution for 2..."
    Returns a dictionary where keys are problem IDs and values are
    dictionaries containing 'problem' and 'solution' strings.
    Returns None if the file is not found, is not a valid YAML dictionary,
    or contains no valid problems.
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            problems_cfg = yaml.safe_load(f)

        if not isinstance(problems_cfg, dict):
             print(f"!!! ERROR [Loader]: Invalid YAML format in {filepath}. Expected a top-level dictionary of problems.")
             return None

        valid_problems: Dict[str, Dict[str, str]] = {}
        for problem_id, content in problems_cfg.items():
            if isinstance(content, dict) and \
               isinstance(content.get('problem'), str) and \
               isinstance(content.get('solution'), str) and \
               content['problem'].strip() and \
               content['solution'].strip(): # Ensure they are non-empty strings
                valid_problems[str(problem_id)] = { # Ensure problem_id is a string
                    'problem': content['problem'],
                    'solution': content['solution']
                }
            else:
                print(f"!!! WARN [Loader]: Problem ID '{problem_id}' in {filepath} has invalid format, is missing, or has empty 'problem'/'solution'. Skipping.")
        
        if not valid_problems:
            print(f"!!! INFO [Loader]: No valid problems found in {filepath} after validation.")
            return None # Or return {} if an empty dict is preferred over None for "no valid problems"
            
        print(f"--- LOADER: Loaded {len(valid_problems)} valid problems from {filepath}")
        return valid_problems

    except FileNotFoundError:
        print(f"!!! ERROR [Loader]: Problem context file not found: {filepath}")
        return None
    except yaml.YAMLError as e:
        print(f"!!! ERROR [Loader]: Error parsing YAML file {filepath}: {e}")
        return None
    except Exception as e:
        print(f"!!! ERROR [Loader]: Unexpected error loading problem context from {filepath}: {e}")
        traceback.print_exc() # Print full traceback for unexpected errors
        return None