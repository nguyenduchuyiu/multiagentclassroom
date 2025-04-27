# llm_service.py
import requests
import os
from google import genai
from google.genai import types

class LLMService:
    def __init__(self, model_name: str, **config):
        self.api_key = os.environ.get("GOOGLE_API_KEY")
        self.client = genai.Client(api_key=self.api_key)
        self.model = model_name
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
         
# def my_tool(string: str):
#     """Args:
#         string: whatever you want
#         return string in uppercase
#     """
#     return string.upper()   

# llm = LLMService(model_name="gemini-2.0-flash", temperature=0.2, system_instruction="Call tool if user tell", tools=[my_tool])
# llm.generate("Hi im Huy, discribe what does tool do")
