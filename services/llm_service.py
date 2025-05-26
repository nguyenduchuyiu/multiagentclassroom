# llm_service.py
import requests
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
load_dotenv()
from tenacity import retry, stop_after_attempt, wait_fixed, before_sleep_log
import logging
from dotenv import load_dotenv
load_dotenv()

# Cấu hình logger
# logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO)  # hoặc DEBUG để log chi tiết hơn


class LLMService:
    def __init__(self, **config):
        self.api_key = os.environ.get("GOOGLE_API_KEY")
        self.client = genai.Client(api_key=self.api_key)
        self.model = config.pop("model", "gemini-2.0-flash")
        self.config = types.GenerateContentConfig(**config)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(2),
        # before_sleep=before_sleep_log(logger, logging.WARNING)  # In log mỗi lần retry
    )
    def generate(self, prompt: str) -> str:
        """Gọi LLM API và trả về text response, retry tối đa 3 lần nếu lỗi."""
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self.config
            )
            return response.text
        except requests.exceptions.RequestException as e:
            print(f"LLM API Request Error: {e}")
            raise
        except Exception as e:
            print(f"Unexpected error in LLM service: {e}")
            raise

         
# ---Testing site---
# def ask_dad(string: str):
#     """Args:
#         string: ask dad about solutions
#         return legit answer
#     """
#     llm = LLMService(model="gemini-2.0-flash", temperature=0)
#     return llm.generate(f"Solve this problem: {string}")

# llm = LLMService(model="gemini-2.0-flash", temperature=2, system_instruction="Answer user questions, ask dad if needed, and told me if you ask dad", tools=[ask_dad])
# print(llm.generate('''Hi im Huy, solve Sure! Here's a nice one \n:
#                         > **Compute the integral:**  
#                         > \[
#                         > \int (3x^2 - 4x + 5) \, dx
#                         > \]

#                         '''))
# test_prompt = '''
# --- System instruction ---:
# Role: Bạn là Khánh – một sinh viên nam 20 tuổi học UET. Là bạn của Nam và Huy.

# Goal: Trò chuyện

# Backstory: Bạn là một chúa hề và mới nhận việc intern remote không lương ở một công ty startup bên Singapore. Hay nói bậy một chút.

# --- Rules ---:

# Bạn có thể tách câu để follow up bằng dấu ' ||| '.
# Ví dụ: Ừ, nghe vui đấy! ||| Nhưng có chắc không vậy?


# --- Tasks:
# 1. khanh_chat: Hãy tham gia trò chuyện sôi nổi với các bạn. Nếu người khác được hỏi đích danh, hãy im lặng và lắng nghe. Nếu không muốn trả lời hãy trả về {{"response": "NO_RESPONSE"}}. Chỉ trả về lời nói, không thêm gì hơn. Gọi người khác là {name} Và nói ngắn thôi để phù hợp với việc chat qua lại. Trả về định dạng json như sau {{"response": "lời nói"}} và không được nói gì thêm.


# --- Recent chat history:
# System: Chào mừng! Vui lòng nhập tên của bạn để bắt đầu.
# Huy: chao vk

# --- Last message:
# chao vk \n

# Hãy phản hồi phù hợp:
# '''
# llm = LLMService(model="gemini-2.0-flash")
# print(llm.generate(test_prompt))

