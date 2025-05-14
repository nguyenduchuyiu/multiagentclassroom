import time
import uuid
import json
import re


def get_timestamp():
    return int(time.time() * 1000)

def generate_uuid():
    return str(uuid.uuid4())

def clean_response(raw_response):
    """Xử lý các ký tự đặc biệt và markdown artifacts"""
    cleaned = re.sub(r'```(json)?', '', raw_response)
    cleaned = cleaned.replace('\r\n', '\n').replace('\r', '\n')
    cleaned = re.sub(
        r'(?<!\\)\\(?!["\\/bfnrt]|u[0-9a-fA-F]{4})', 
        r'\\\\', 
        cleaned
    )
    return cleaned.strip()

def parse_json_response(cleaned_response):
    """Xử lý và validate JSON response"""
    try:
        return json.loads(cleaned_response)
    except json.JSONDecodeError:
        # Try to extract JSON from the text
        start = cleaned_response.find('{')
        end = cleaned_response.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(cleaned_response[start:end+1])
            except:
                pass
        # Fallback response
        return None

def process_content(content):
    """Chuyển đổi định dạng markdown sang HTML"""
    # Xử lý bullet points và số thứ tự
    content = re.sub(r'(\d+\.)\s', r'<span class="list-number">\1</span> ', content)
    content = re.sub(r'•\s', r'<span class="list-bullet">•</span> ', content)
    
    # Fix căn bậc 2
    content = re.sub(r'\\sqrt(\w+)', r'\\sqrt{\1}', content)
    
    # Xử lý in đậm với dấu **
    content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
    
    # Thêm khoảng trắng sau dấu $
    content = re.sub(r'\$(?! )', '$ ', content)
    content = re.sub(r'(?<! )\$', ' $', content)
    
    # Xử lý thụt đầu dòng
    content = re.sub(r'\n\s{2,}', lambda m: '\n' + ' ' * (len(m.group(0))//2), content)
    
    # Thay thế các ký tự bullet đặc biệt
    bullet_replacements = {'◦': '○', '■': '▪', '‣': '▸'}
    for k, v in bullet_replacements.items():
        content = content.replace(k, v)
    
    return content
    
def parse_output(content):
    cleaned_response = clean_response(content)
    # Parse JSON response
    response_data = parse_json_response(cleaned_response)
    # Process content with LaTeX formatting
    bot_response = process_content(response_data.get("spoken_message", ""))
    return bot_response
