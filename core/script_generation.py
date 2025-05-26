from services.llm_service import LLMService
from typing import Dict
import os
import yaml
from core.prompt_templates import SCRIPT_GENERATION_PROMPT, ROLE_GENERATION_PROMPT

class ScriptGeneration:
    def __init__(self, problem_description: str, solution: str, config: Dict = None, keywords: list[str] = None):
        self.problem = problem_description
        self.solution = solution
        self.llm_service = LLMService(model="gemini-2.0-flash", temperature=1)
        self.config = config or {}
        self.keywords = keywords or []

    def _format_keywords_for_prompt(self) -> str:
        if not self.keywords:
            return "Không có từ khóa nào được cung cấp."
        return "- " + "\n- ".join(self.keywords)

    def generate_script(self):
        formatted_solution = self._format_solution_for_prompt(self.solution)
        keywords_str = self._format_keywords_for_prompt()
        prompt = SCRIPT_GENERATION_PROMPT.format(
            problem=self.problem, 
            solution=formatted_solution,
            keywords_str=keywords_str
        )
        return self.llm_service.generate(prompt)
    
    def generate_roles(self, script_yaml_str: str):
        """Generates AI character roles based on the ROLE_GENERATION_PROMPT."""
        formatted_solution = self._format_solution_for_prompt(self.solution)
        keywords_str = self._format_keywords_for_prompt()
        prompt = ROLE_GENERATION_PROMPT.format(
            problem=self.problem, 
            solution=formatted_solution, 
            script=script_yaml_str,
            keywords_str=keywords_str
        )
        return self.llm_service.generate(prompt)

    def _format_solution_for_prompt(self, solution: str) -> str:
        return f"**SOLUTION:**\n{solution}"


# if __name__ == "__main__":

#     CONFIG_DIR = "config"
#     PHASES_FILE = os.path.join(CONFIG_DIR, "phases.yaml")
#     PERSONAS_FILE = os.path.join(CONFIG_DIR, "personas.yaml")
#     PROBLEM_CONTEXT_FILE = os.path.join(CONFIG_DIR, "problem_context.yaml")

#     # Ensure config directory exists
#     os.makedirs(CONFIG_DIR, exist_ok=True)
#     try:
#         with open(PROBLEM_CONTEXT_FILE, "r", encoding="utf-8") as f:
#             problem_context = yaml.safe_load(f)
#     except FileNotFoundError:
#         print(f"Error: {PROBLEM_CONTEXT_FILE} not found. Please create it with 'problem' and 'solution' keys.")
#         exit()
#     except yaml.YAMLError as e:
#         print(f"Error parsing {PROBLEM_CONTEXT_FILE}: {e}")
#         exit()

#     problem = problem_context.get("problem")
#     solution = problem_context.get("solution")

#     if not problem or not solution:
#         print(f"Error: 'problem' or 'solution' not found in {PROBLEM_CONTEXT_FILE}.")
#         exit()

#     # Define some keywords for creative generation
#     creative_keywords = input("Enter creative keywords (comma-separated): ").split(",")
#     creative_keywords = [keyword.strip() for keyword in creative_keywords] #remove whitespace
#     # You can also load these from a file or user input

#     script_generator = ScriptGeneration(
#         problem_description=problem, 
#         solution=solution, 
#         keywords=creative_keywords
#     )

#     # Generate and save script (phases)
#     print("Generating script (phases)...")
#     phases_yaml_str = script_generator.generate_script()
#     phases_yaml_str = phases_yaml_str.replace("```yaml", "").replace("```", "")
#     try:
#         # Validate if the output is YAML before writing (optional, but good practice)
#         # yaml.safe_load(phases_yaml_str) 
#         with open(PHASES_FILE, "w", encoding="utf-8") as f:
#             f.write(phases_yaml_str)
#         print(f"Script (phases) saved to {PHASES_FILE}")
#         # print("\n--- Generated Phases ---")
#         # print(phases_yaml_str)
#     except yaml.YAMLError as e:
#         print(f"Error: The generated script is not valid YAML: {e}")
#     except Exception as e:
#         print(f"Error saving script (phases): {e}")

#     # Generate and save roles (personas)
#     print("\nGenerating roles (personas)...")
#     personas_yaml_str = script_generator.generate_roles(script_yaml_str=phases_yaml_str)
#     personas_yaml_str = personas_yaml_str.replace("```yaml", "").replace("```", "")
#     try:
#         # Validate if the output is YAML before writing (optional)
#         # yaml.safe_load(personas_yaml_str)
#         with open(PERSONAS_FILE, "w", encoding="utf-8") as f:
#             f.write(personas_yaml_str)
#         print(f"Roles (personas) saved to {PERSONAS_FILE}")
#         # print("\n--- Generated Personas ---")
#         # print(personas_yaml_str)
#     except yaml.YAMLError as e:
#         print(f"Error: The generated roles are not valid YAML: {e}")
#     except Exception as e:
#         print(f"Error saving roles (personas): {e}")
