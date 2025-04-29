# Default IO Handler
import json

# Constants
RULES_TEXT = '''
Bạn có thể tách câu để follow up bằng dấu ' ||| '.
Ví dụ: Ừ, nghe vui đấy! ||| Nhưng có chắc không vậy?
'''

class DefaultIOHandler:
    def __init__(self, prompt_template: str):
        self.template = prompt_template

    def parse_input(self, raw_kwargs, conversation):
        history = conversation.get_recent_history()
        return {
            'history': history,
            **raw_kwargs
        }

    def build_prompt(self, parsed, system_instruction, tasks):
        history_text = "\n".join(
            f"{m['sender']}: {m['text']}" for m in parsed['history']
        )
        tasks_text = "\n".join(
            f"{i+1}. {name}: {info['description']}"
            for i, (name, info) in enumerate(tasks.items())
        )
        last_message = parsed['history'][-1]['text'] if parsed['history'] else ""
        return self.template.format(
            system_instruction=system_instruction,
            rules=RULES_TEXT,
            tasks=tasks_text,
            history=history_text,
            last_message=last_message
        )

    def parse_output(self, llm_raw: str):
        print(llm_raw)
        data = json.loads(llm_raw.replace("```json", "").replace("```", "").strip("").replace("{{", "{").replace("}}", "}"))
        resp = data.get("response", "").strip()
        if not resp or resp.upper() == "NO_RESPONSE":
            return []
        return [s.strip() for s in resp.split(" ||| ") if s.strip()]