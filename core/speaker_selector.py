# core/speaker_selector.py
import random
import json
import traceback
from typing import List, Dict, Any, Optional, Tuple
from core.conversation_history import ConversationHistory # Keep for history formatting
from services.llm_service import LLMService # Added
from core.prompt_templates import THOUGHTS_EVALUATOR_PROMPT


class SpeakerSelector:
    def __init__(self, problem_description: str, llm_service: LLMService, config: Dict = None):
        self.problem = problem_description
        self.llm_service = llm_service
        self.config = config or {}
        self.lambda_weight = self.config.get("lambda_weight", 0.5)
        # No direct app instance needed here unless _call_evaluator_llm needs context for some reason

    def _format_history_for_prompt(self, history: List[Dict], count=15) -> str:
        recent_history = history[-count:]
        lines = []
        for i, event in enumerate(recent_history):
             text = event.get('content', {}).get('text', '(Non-message event)')
             source_display = event.get('content', {}).get('sender_name', event.get('source', 'Unknown'))
             lines.append(f"CON#{i+1} {source_display}: {text}")
        return "\n".join(lines) if lines else "Chưa có hội thoại."

    def _format_thoughts_for_prompt(self, thinking_results: List[Dict[str, Any]]) -> str:
        lines = []
        for result in thinking_results:
             if result and result.get("action_intention") == "speak":
                 lines.append(f"- {result.get('agent_name', 'Unknown')}: {result.get('thought', '')}")
        return "\n".join(lines) if lines else "Không có ai muốn nói."

    def _call_evaluator_llm(self, prompt: str) -> List[Dict[str, Any]]:
        """Calls the LLM to get evaluation scores."""
        # This method itself doesn't need app context unless LLMService uses 'g'
        # Assuming LLMService uses its own client directly.
        # print("--- SPEAKER_SELECTOR: Requesting evaluation from LLM...")
        try:
            raw_response = self.llm_service.generate(prompt)
            # print(f"--- SPEAKER_SELECTOR: Raw LLM Evaluation Response: {raw_response}")
            clean_response = raw_response.strip()
            if clean_response.startswith("```json"): clean_response = clean_response[7:]
            if clean_response.endswith("```"): clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            parsed_scores = json.loads(clean_response)
            if not isinstance(parsed_scores, list): raise ValueError("LLM did not return a list.")
            validated_scores = []
            for item in parsed_scores:
                if isinstance(item, dict) and 'name' in item and 'score' in item and 'internal_score' in item and 'external_score' in item:
                     try:
                         item['internal_score'] = float(item['internal_score'])
                         item['external_score'] = float(item['external_score'])
                        #  print("====================Score================== ")
                        #  print(item['score'])
                        #  print("====================Score================== ")
                         validated_scores.append(item)
                     except (ValueError, TypeError): print(f"!!! WARN [SpeakerSelector]: Invalid score format for {item.get('name')}. Skipping.")
                else: print(f"!!! WARN [SpeakerSelector]: Invalid score item format: {item}. Skipping.")
            return validated_scores
        except json.JSONDecodeError as e:
            print(f"!!! ERROR [SpeakerSelector]: Failed to parse LLM JSON evaluation response: {e}")
            print(f"Raw response was: {raw_response}")
            return []
        except Exception as e:
            print(f"!!! ERROR [SpeakerSelector]: Unexpected error during evaluation LLM call: {e}")
            traceback.print_exc()
            return []

    def select_speaker(self,
                       session_id: str,
                       thinking_results: List[Dict[str, Any]],
                       phase_context: Dict,
                       conversation_history: List[Dict]) -> Dict[str, Any]: # Takes history LIST now
        """Selects the best agent to act for the session."""
        log_prefix = f"--- SPEAKER_SELECTOR [{session_id}]"
        print(f"{log_prefix}: Evaluating {len(thinking_results)} thinking results...")

        agents_wanting_to_speak = [res for res in thinking_results if res and res.get("action_intention") == "speak"]
        if not agents_wanting_to_speak:
            print(f"{log_prefix}: No agents intend to speak.")
            return {}

        # Format phase description
        phase_desc_prompt = f"Stage {phase_context.get('id', 'N/A')}: {phase_context.get('name', 'Không rõ')}\n"
        phase_desc_prompt += f"Description: {phase_context.get('description', 'Không có mô tả')}\n"
        tasks_list = phase_context.get('tasks', [])
        phase_desc_prompt += "Tasks:\n" + ("\n".join([f"- {t}" for t in tasks_list]) + "\n" if tasks_list else "(Không có nhiệm vụ cụ thể cho giai đoạn này)\n")
        goals_list = phase_context.get('goals', [])
        phase_desc_prompt += "Goals:\n" + ("\n".join([f"- {g}" for g in goals_list]) + "\n" if goals_list else "(Không có mục tiêu cụ thể cho giai đoạn này)\n")

        # Build prompt for evaluator LLM
        prompt = THOUGHTS_EVALUATOR_PROMPT.format(
            list_AI_name=", ".join([res['agent_name'] for res in agents_wanting_to_speak]),
            problem=self.problem,
            current_stage_description=phase_desc_prompt.strip(),
            history=self._format_history_for_prompt(conversation_history), # Use passed list
            AI_thoughts=self._format_thoughts_for_prompt(agents_wanting_to_speak)
        )

        # Get scores from LLM (No app context needed here directly)
        llm_scores = self._call_evaluator_llm(prompt)
        if not llm_scores:
            print(f"{log_prefix}: Failed to get valid scores from LLM.")
            return {}

        # Combine scores
        evaluated_results = []
        llm_scores_map = {score['name']: score for score in llm_scores}
        for result in agents_wanting_to_speak:
            agent_name = result['agent_name']
            scores = llm_scores_map.get(agent_name)
            if scores:
                internal_s, external_s = scores['internal_score'], scores['external_score']
                final_s = ((1 - self.lambda_weight) * internal_s + self.lambda_weight * external_s) + random.uniform(-0.01, 0.01)
                evaluated_results.append({**result, "internal_score": internal_s, "external_score": external_s, "final_score": final_s})
                print(f"{log_prefix}: Score for {agent_name}: Final={final_s:.2f} (IS={internal_s:.2f}, ES={external_s:.2f}) from LLM")
            else: print(f"{log_prefix}: Warning - No LLM score found for {agent_name}. Skipping.")

        if not evaluated_results:
             print(f"{log_prefix}: No agents passed evaluation or scoring.")
             return {}

        # Selection Logic
        evaluated_results.sort(key=lambda x: x["final_score"], reverse=True)
        selected_agent_result = evaluated_results[0]
        # Add threshold check if needed:
        # score_threshold = self.config.get("min_speak_score", 2.5) # Example threshold
        # if selected_agent_result["final_score"] < score_threshold:
        #     print(f"{log_prefix}: Highest score {selected_agent_result['final_score']:.2f} below threshold {score_threshold}. No speaker selected.")
        #     return {}

        print(f"{log_prefix}: Selected {selected_agent_result['agent_name']} with score {selected_agent_result['final_score']:.2f}")

        return {
            "selected_agent_id": selected_agent_result["agent_id"],
            "selected_agent_name": selected_agent_result["agent_name"],
            "selected_action": "speak",
            "selected_thought_details": selected_agent_result,
            "evaluation_scores": {res['agent_id']: res['final_score'] for res in evaluated_results}
        }