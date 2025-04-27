# llm_service.py
import requests
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
load_dotenv()


class LLMService:
    def __init__(self, **config):
        self.api_key = os.environ.get("GOOGLE_API_KEY")
        self.client = genai.Client(api_key=self.api_key)
        self.model = config.pop("model", "gemini-2.0-flash")
        self.config = types.GenerateContentConfig(**config)

    def generate(self, prompt: str) -> str:
        """Gọi LLM API và trả về text response."""
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self.config
            )
            response_text = response.text
            return response_text
        except requests.exceptions.RequestException as e:
            print(f"LLM API Request Error: {e}")
            return "NO_RESPONSE" # Hoặc ném exception để agent xử lý
        except Exception as e:
             print(f"Unexpected error in LLM service: {e}")
             return "NO_RESPONSE"
         
# ---Testing site---
# def ask_dad(string: str):
#     """Args:
#         string: ask dad about solutions
#         return legit answer
#     """
#     llm = LLMService(model="gemini-2.0-flash", temperature=0)
#     return llm.generate(f"Solve this problem: {string}")

# llm = LLMService(model="gemini-2.0-flash", temperature=2, system_instruction="Answer user questions, ask dad if needed, and told me if you ask dad", tools=[ask_dad])
# print(llm.generate('''Hi im Huy, solve Sure! Here's a nice one:
#                         > **Compute the integral:**  
#                         > \[
#                         > \int (3x^2 - 4x + 5) \, dx
#                         > \]

#                         '''))

