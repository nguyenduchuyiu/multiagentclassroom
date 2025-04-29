# core/speaker_selector.py
import random
import json
import traceback
from typing import List, Dict, Any, Optional, Tuple
from core.conversation_history import ConversationHistory # Keep for history formatting
from services.llm_service import LLMService # Added

# Import the prompt template
THOUGHTS_EVALUATOR_PROMPT = """
## Role
Bạn là người đánh giá các suy nghĩ của các bạn học khi tham gia vào thảo luận nhóm.

## Goal
Mục tiêu của bạn là chấm điểm những suy nghĩ đó dựa trên thang điểm (1.0 - 5.0), để chọn ra đâu là suy nghĩ hợp lý nhất của một bạn học để thực hiện nói trong lượt tiếp theo.

## Backstory
Bạn được thiết kế dựa trên sự kết hợp giữa tâm lý học giáo dục và phân tích các mẫu hình giao tiếp trong làm việc nhóm, chuyên sâu vào việc đánh giá các động lực nội tại thúc đẩy một cá nhân muốn phát biểu, cũng như các yếu tố xã hội ảnh hưởng đến thời điểm thích hợp để tham gia. Mục tiêu là cung cấp một đánh giá khách quan và tinh tế, xác định ai có khả năng và mong muốn đóng góp ý nghĩa nhất vào cuộc trò chuyện tại mỗi thời điểm, qua đó thúc đẩy các cuộc thảo luận cân bằng và hiệu quả.

## Tasks
### Mô tả nhiệm vụ:
Bạn được cung cấp :
- Cuộc hội thoại giữa một nhóm bạn.
- Những suy nghĩ từ các bạn học sau: {list_AI_name}. Những suy nghĩ này phản ánh
- Mô tả về nhiệm vụ (STEP) trong stage bài toán.

Việc bạn cần làm là đánh giá từng suy nghĩ đó theo hướng dẫn dưới đây. Đảm bảo là bạn hiểu hướng dẫn và thực hiện đúng.

### Tiêu chí đánh giá:
Chấm điểm động lực nội tại của từng bạn học để xác định "nếu là họ, bạn có muốn bày tỏ suy nghĩ và có khả năng tham gia vào nói chuyện ngay bây giờ không?":
- 1 (Thấp) : rất khó có khả năng bày tỏ suy nghĩ và tham gia vào cuộc trò chuyện tại thời điểm này. Họ gần như chắc chắn sẽ im lặng.
- 2 (Trung lập) : trung lập về việc bày tỏ suy nghĩ và tham gia vào cuộc trò chuyện tại thời điểm này. Họ ổn với việc bày tỏ suy nghĩ hoặc im lặng và để người khác nói.
- 3 (Cao) : có khả năng bày tỏ suy nghĩ và tham gia vào cuộc trò chuyện tại thời điểm này. Họ có mong muốn mạnh mẽ được tham gia ngay sau khi người nói hiện tại kết thúc lượt của mình.
- 4 (Rất cao) : Họ thậm chí sẽ ngắt lời những người khác đang nói vì có một việc rất quan trọng (ví dụ ai đó mắc lỗi sai).
- 5 (Cấp bách): Họ PHẢI nói ngay lập tức, ví dụ như sửa lỗi nghiêm trọng hoặc ngăn chặn hướng đi sai lầm. (Added 5.0 for clarity)


### Các bước đánh giá:
1. Đọc kỹ cuộc trò chuyện trước đó và suy nghĩ được hình thành bởi người bạn đang đánh giá.
2. Đánh giá suy nghĩ dựa trên hai loại yếu tố sau:
2.1. Các yếu tố từ bên trong cá nhân của họ (internal_score):
    (a) Khoảng cách thông tin: Suy nghĩ có chỉ ra rằng đang gặp phải khoảng cách thông tin tại thời điểm trò chuyện không? Ví dụ, có thắc mắc, tò mò, bối rối, mong muốn làm rõ hoặc hiểu lầm.
    (b) Lấp đầy khoảng cách thông tin: Suy nghĩ có chứa thông tin quan trọng để lấp đầy khoảng cách thông tin trong cuộc trò chuyện không? Ví dụ, bằng cách trả lời một câu hỏi, bổ sung và cung cấp thông tin bổ sung, thêm phần làm rõ và giải thích. Những suy nghĩ trả lời trực tiếp một câu hỏi được đặt ra trong cuộc trò chuyện sẽ nhận được đánh giá cao ở đây.
    (c) Tác động mong đợi: Tác động của suy nghĩ đối với cuộc trò chuyện đang diễn ra có ý nghĩa như thế nào? Ví dụ, có khả năng chuyển bước làm mới, thu hút sự quan tâm của người khác và kích thích các cuộc thảo luận trong tương lai.
    (d) Tính cấp thiết: Suy nghĩ có cần phải được diễn đạt ngay lập tức không? Ví dụ, vì nó cung cấp thông tin quan trọng, cảnh báo người tham gia về các chi tiết quan trọng hoặc sửa các hiểu lầm hoặc lỗi quan trọng.
2.2. Các yếu tố xã hội bên ngoài (external_score):
    (e) Tính mạch lạc với phát ngôn cuối cùng: Suy nghĩ có vẻ hợp lý nếu nó được diễn đạt ngay sau đó trong cuộc trò chuyện và là phản hồi hợp lý và tức thời cho phát ngôn cuối cùng không? Ví dụ, không phù hợp để tham gia khi suy nghĩ nằm ngoài ngữ cảnh, không liên quan hoặc bỏ qua câu hỏi của người nói trước.
    (f) Tính lặp lại: Suy nghĩ có cung cấp thông tin mới và nguyên bản không, và tránh thông tin trùng lặp và lặp lại hành động của người khác đã được đề cập trong cuộc trò chuyện trước đó không?
    (g) Cân bằng: Mọi người có cơ hội tham gia vào cuộc trò chuyện và không bị bỏ rơi không? Ví dụ, một vài phát biểu cuối cùng được thống trị giữa hai người tham gia và một người đã không nói trong một thời gian.
    (h) Động lực: Có ai đó khác có thể có điều gì đó để nói hoặc đang tích cực đóng góp cho cuộc trò chuyện không? Ví dụ: nếu một người nhận thấy người khác có mong muốn mạnh mẽ để nói, họ có thể giữ lại suy nghĩ của mình và chờ đợi để tham gia.

### Hướng dẫn quan trọng:
1. Sử dụng thang đánh giá ĐẦY ĐỦ từ 1.0 đến 5.0. KHÔNG mặc định ở mức đánh giá trung bình (3.0-4.0).
2. Quyết đoán và phê phán - một số suy nghĩ đáng được đánh giá rất thấp (1.0-2.0) và một số khác đáng được đánh giá rất cao (4.0-5.0).
3. Những suy nghĩ chung chung mà bất kỳ ai cũng có thể có nên được đánh giá thấp hơn những suy nghĩ có ý nghĩa cá nhân.
4. Sử dụng số thập phân (ví dụ: 2.7, 4.2) để đánh giá điểm động lực nội tại của từng suy nghĩ.
5. Mỗi yếu tố có mặt tích cực có thể cộng thêm 0,1-0,3 và mỗi yếu tố có mặt tiêu cực có thể trừ 0,1-0,3 vào điểm số. (This part is for the LLM's internal logic, not for us to implement directly).

## Bạn nhận được:
### Đây là bài toán đang thảo luận:
---
{problem}
---
### Mô tả chi tiết nhiệm vụ, mục tiêu của stage bài toán hiện tại:
---
{current_stage_description}
---
### Cuộc hội thoại:
---
{history}
---
### Suy nghĩ của từng bạn học cần đánh giá:
---
{AI_thoughts}
---

## Định dạng đầu ra:
Chỉ trả về JSON với định dạng sau mà KHÔNG nói bất kỳ gì thêm, trả về đúng tên và số lượng bạn học cần đánh giá:
```json
[
    {{"name" : "<tên>", "internal_score" : <1.0-5.0>, "external_score" : <1.0-5.0>}},
    {{"name" : "<tên>", "internal_score" : <1.0-5.0>, "external_score" : <1.0-5.0>}},
    {{"name" : "<tên>", "internal_score" : <1.0-5.0>, "external_score" : <1.0-5.0>}}
]
"""

class SpeakerSelector:
    # ... (__init__, _format_history_for_prompt, _format_thoughts_for_prompt, _call_evaluator_llm - remain the same) ...
    def __init__(self, problem_description: str, llm_service: LLMService, config: Dict = None):
        self.problem = problem_description
        self.llm_service = llm_service
        self.config = config or {}
        self.lambda_weight = self.config.get("lambda_weight", 0.5)

    def _format_history_for_prompt(self, history: List[Dict], count=15) -> str:
        # ... (implementation remains the same) ...
        recent_history = history[-count:]
        lines = []
        for i, event in enumerate(recent_history):
             text = event.get('content', {}).get('text', '(Non-message event)')
             source = event.get('source', 'Unknown')
             lines.append(f"CON#{i+1} {source}: {text}")
        return "\n".join(lines) if lines else "Chưa có hội thoại."

    def _format_thoughts_for_prompt(self, thinking_results: List[Dict[str, Any]]) -> str:
        # ... (implementation remains the same) ...
        lines = []
        for result in thinking_results:
             if result and result.get("action_intention") == "speak":
                 lines.append(f"- {result.get('agent_name', 'Unknown')}: {result.get('thought', '')}")
        return "\n".join(lines) if lines else "Không có ai muốn nói."

    def _call_evaluator_llm(self, prompt: str) -> List[Dict[str, Any]]:
        # ... (implementation remains the same) ...
        print("--- SPEAKER_SELECTOR: Requesting evaluation from LLM...")
        try:
            raw_response = self.llm_service.generate(prompt)
            print(f"--- SPEAKER_SELECTOR: Raw LLM Evaluation Response: {raw_response}")
            clean_response = raw_response.strip().replace("```json", "").replace("```", "")
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
            return []
        except Exception as e:
            print(f"!!! ERROR [SpeakerSelector]: Unexpected error during evaluation LLM call: {e}")
            traceback.print_exc()
            return []

    # <<< Add session_id parameter >>>
    def select_speaker(self,
                       session_id: str, # Added
                       thinking_results: List[Dict[str, Any]],
                       phase_context: Dict,
                       conversation_history: List[Dict]) -> Dict[str, Any]: # Takes history LIST now
        """
        Uses the THOUGHTS_EVALUATOR LLM prompt to get scores and selects the best agent for the session.
        """
        # Include session_id in log messages
        log_prefix = f"--- SPEAKER_SELECTOR [{session_id}]"
        print(f"{log_prefix}: Evaluating {len(thinking_results)} thinking results...")

        agents_wanting_to_speak = [res for res in thinking_results if res and res.get("action_intention") == "speak"]
        if not agents_wanting_to_speak:
            print(f"{log_prefix}: No agents intend to speak.")
            return {}

        # Format phase description (remains the same logic)
        phase_desc_prompt = f"Stage {phase_context.get('id', 'N/A')}: {phase_context.get('name', '')}\n..." # (rest of formatting)
        phase_desc_prompt += f"Description: {phase_context.get('description', '')}\n"
        phase_desc_prompt += "Tasks:\n" + "\n".join([f"- {t}" for t in phase_context.get('tasks', [])]) + "\n"
        phase_desc_prompt += "Goals:\n" + "\n".join([f"- {g}" for g in phase_context.get('goals', [])])

        # Build prompt (remains the same logic, uses passed history list)
        prompt = THOUGHTS_EVALUATOR_PROMPT.format(
            list_AI_name=", ".join([res['agent_name'] for res in agents_wanting_to_speak]),
            problem=self.problem,
            current_stage_description=phase_desc_prompt.strip(),
            history=self._format_history_for_prompt(conversation_history), # Use passed history list
            AI_thoughts=self._format_thoughts_for_prompt(agents_wanting_to_speak)
        )

        llm_scores = self._call_evaluator_llm(prompt)
        if not llm_scores:
            print(f"{log_prefix}: Failed to get valid scores from LLM.")
            return {}

        # Combine scores (remains the same logic)
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

        evaluated_results.sort(key=lambda x: x["final_score"], reverse=True)
        selected_agent_result = evaluated_results[0]
        print(f"{log_prefix}: Selected {selected_agent_result['agent_name']} with score {selected_agent_result['final_score']:.2f}")

        return {
            "selected_agent_id": selected_agent_result["agent_id"],
            "selected_agent_name": selected_agent_result["agent_name"],
            "selected_action": "speak",
            "selected_thought_details": selected_agent_result,
            "evaluation_scores": {res['agent_id']: res['final_score'] for res in evaluated_results}
        }