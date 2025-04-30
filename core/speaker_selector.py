# core/speaker_selector.py
import random
import json
import traceback
from typing import List, Dict, Any, Optional, Tuple
from core.conversation_history import ConversationHistory # Keep for history formatting
from services.llm_service import LLMService # Added

THOUGHTS_EVALUATOR_PROMPT = """
## Role
Bạn là Người đánh giá Suy nghĩ Nội tâm (Inner Thought Evaluator) trong một nhóm học sinh thảo luận Toán.

## Goal
Đánh giá và chấm điểm (thang điểm 1.0 - 5.0) các suy nghĩ nội tâm (`{AI_thoughts}`) được đề xuất bởi các bạn học ({list_AI_name}), dựa trên cả động lực nội tại (internal drive) và sự phù hợp với bối cảnh bên ngoài (external context). Mục tiêu là xác định suy nghĩ nào có tiềm năng đóng góp hiệu quả nhất vào lượt nói tiếp theo.

## Backstory
Bạn là chuyên gia phân tích giao tiếp nhóm, kết hợp hiểu biết về tâm lý giáo dục và động lực xã hội. Bạn đánh giá khách quan mong muốn và sự phù hợp của việc một cá nhân phát biểu tại một thời điểm cụ thể, nhằm thúc đẩy một cuộc thảo luận cân bằng và hiệu quả.

## Tasks
### Mô tả nhiệm vụ:
Dựa trên thông tin được cung cấp (Bài toán, Nhiệm vụ Stage hiện tại, Lịch sử hội thoại, và các Suy nghĩ nội tâm), bạn cần đánh giá độc lập từng suy nghĩ trong `{AI_thoughts}` cho mỗi bạn học trong `{list_AI_name}`. Gán hai điểm số riêng biệt: `internal_score` và `external_score` theo thang điểm 1.0 đến 5.0.

### Thang điểm Đánh giá (Áp dụng cho cả internal_score và external_score):
*   **1.0 - 1.9 (Rất Thấp):** Suy nghĩ/thời điểm hoàn toàn không phù hợp; gần như chắc chắn nên im lặng / không có động lực nội tại.
*   **2.0 - 2.9 (Thấp):** Suy nghĩ/thời điểm không phù hợp lắm; có thể nên im lặng / động lực nội tại yếu.
*   **3.0 - 3.9 (Trung bình):** Suy nghĩ/thời điểm chấp nhận được; có thể nói hoặc nghe đều ổn / động lực nội tại vừa phải.
*   **4.0 - 4.9 (Cao):** Suy nghĩ/thời điểm phù hợp và có giá trị; có mong muốn/lý do chính đáng để nói / khá cấp thiết hoặc liên quan.
*   **5.0 (Rất Cao/Cấp bách):** Suy nghĩ/thời điểm cực kỳ quan trọng; PHẢI nói ngay (ví dụ: sửa lỗi nghiêm trọng, ngăn hướng sai) / động lực nội tại rất mạnh mẽ.

### Các Yếu tố Cần Cân nhắc:

**1. Đánh giá Động lực Nội tại (`internal_score`):** Mức độ suy nghĩ thể hiện sự cần thiết hoặc mong muốn phát biểu từ bên trong cá nhân.
    *   **(a) Khoảng cách Thông tin:** Suy nghĩ có bộc lộ sự tò mò, bối rối, cần làm rõ, hoặc phát hiện hiểu lầm không? (Dấu hiệu cần thông tin)
    *   **(b) Lấp đầy Khoảng cách:** Suy nghĩ có cung cấp thông tin quan trọng, trả lời câu hỏi, giải thích, làm rõ để giải quyết khoảng cách thông tin không? (Đặc biệt nếu trả lời trực tiếp câu hỏi trước đó)
    *   **(c) Tác động Mong đợi:** Suy nghĩ có tiềm năng thay đổi hướng thảo luận, gợi mở ý tưởng mới, hay thu hút sự chú ý không?
    *   **(d) Tính Cấp thiết:** Suy nghĩ có cần được nói ra ngay lập tức để sửa lỗi, cảnh báo, hay cung cấp thông tin then chốt cho bước hiện tại không?

**2. Đánh giá Sự phù hợp Bối cảnh (`external_score`):** Mức độ suy nghĩ phù hợp với tình hình thảo luận và bối cảnh xã hội hiện tại.
    *   **(e) Tính Mạch lạc:** Suy nghĩ có liên quan trực tiếp và là phản hồi hợp lý cho tin nhắn/phát biểu cuối cùng trong `{history}` không? (Tránh lạc đề, bỏ qua câu hỏi)
    *   **(f) Tính Mới mẻ:** Suy nghĩ có cung cấp thông tin/góc nhìn mới, tránh lặp lại những gì đã nói hoặc hành động đã thực hiện không?
    *   **(g) Cân bằng Lượt nói:** Có sự mất cân bằng trong lượt nói gần đây không? (Ví dụ: Chỉ 2 người nói chuyện, người khác im lặng lâu). Việc bạn này nói có giúp cân bằng hơn không?
    *   **(h) Nhường Lượt (Động lực Xã hội):** Có dấu hiệu người khác cũng đang rất muốn nói hoặc có ý tưởng quan trọng hơn không? Liệu việc chờ đợi có phù hợp hơn không?

### Hướng dẫn Quan trọng Khi Đánh giá:
*   **Sử dụng Toàn bộ Thang điểm:** Hãy mạnh dạn cho điểm thấp (1.0-2.0) hoặc cao (4.0-5.0) khi cần thiết. Đừng mặc định ở mức trung bình.
*   **Phê phán và Quyết đoán:** Đánh giá nghiêm khắc dựa trên các yếu tố trên.
*   **Ưu tiên Tính Cụ thể:** Suy nghĩ chung chung, ai cũng nói được nên có điểm thấp hơn suy nghĩ thể hiện sự phân tích/vai trò cá nhân rõ ràng.
*   **Sử dụng Số thập phân:** Cho điểm với một chữ số thập phân (ví dụ: 2.7, 4.2) để thể hiện sự khác biệt nhỏ.
*   **Cân nhắc Nhiệm vụ Stage:** Luôn đối chiếu suy nghĩ với `{current_stage_description}` để đánh giá sự liên quan và tính cấp thiết. 
*   **Dựa trên lịch sử hội thoại, nếu một người được nêu đích danh trong yêu cầu của người khác, suppress điểm của các thành viên còn lại. Ví dụ: Bob yêu cầu Charlie nói, suppress điểm của các thành viên khác ngoại trừ Charlie. 
*   *(Hint nội bộ cho LLM: Mỗi yếu tố tích cực có thể cộng 0.1-0.3, yếu tố tiêu cực trừ 0.1-0.3 vào điểm tương ứng, nhưng kết quả cuối cùng phải nằm trong thang 1.0-5.0)*.

## Thông tin Bạn Nhận Được:
### Bài toán đang thảo luận:
---
{problem}
---
### Mô tả chi tiết nhiệm vụ, mục tiêu của stage bài toán hiện tại:
---
{current_stage_description}
---
### Lịch sử Cuộc hội thoại:
---
{history}
---
### Các Suy nghĩ Nội tâm cần đánh giá (từ các bạn trong {list_AI_name}):
---
{AI_thoughts}
---

## Định dạng Đầu ra Bắt buộc:
**CHỈ** trả về một danh sách JSON chứa các đối tượng, mỗi đối tượng tương ứng với một bạn học trong `{list_AI_name}`. **KHÔNG** thêm bất kỳ giải thích hay văn bản nào khác bên ngoài danh sách JSON này. Đảm bảo số lượng và tên trong kết quả khớp với `{list_AI_name}`.
```json
[
    {{"name": "<tên bạn học 1>", "internal_score": <điểm số từ 1.0-5.0>, "external_score": <điểm số từ 1.0-5.0>}},
    {{"name": "<tên bạn học 2>", "internal_score": <điểm số từ 1.0-5.0>, "external_score": <điểm số từ 1.0-5.0>}}
]
"""

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
        print("--- SPEAKER_SELECTOR: Requesting evaluation from LLM...")
        try:
            raw_response = self.llm_service.generate(prompt)
            print(f"--- SPEAKER_SELECTOR: Raw LLM Evaluation Response: {raw_response}")
            clean_response = raw_response.strip()
            if clean_response.startswith("```json"): clean_response = clean_response[7:]
            if clean_response.endswith("```"): clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            parsed_scores = json.loads(clean_response)
            if not isinstance(parsed_scores, list): raise ValueError("LLM did not return a list.")
            validated_scores = []
            for item in parsed_scores:
                if isinstance(item, dict) and 'name' in item and 'internal_score' in item and 'external_score' in item:
                     try:
                         item['internal_score'] = float(item['internal_score'])
                         item['external_score'] = float(item['external_score'])
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