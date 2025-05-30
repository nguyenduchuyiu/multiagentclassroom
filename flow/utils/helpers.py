import random
import yaml

import time
import uuid
import json
import re


def get_timestamp():
    return int(time.time() * 1000)

def generate_uuid():
    return str(uuid.uuid4())

def clean_response(raw_response):
    """Xử lý các ký tự đặc biệt json, yaml, html, markdown artifacts"""
    cleaned = re.sub(r'```(json|yaml|html|markdown)?', '', raw_response)
    cleaned = cleaned.replace('<\html>', '').replace('</html>', '')
    cleaned = cleaned.replace('\r\n', '\n').replace('\r', '\n')
    # Remove double curly braces at start/end
    cleaned = re.sub(r'^\s*\{\{', '{', cleaned)
    cleaned = re.sub(r'\}\}\s*$', '}', cleaned)
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
    except Exception as e:
        print(cleaned_response)
        print(f"Error parsing JSON: {e}")
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
    
def parse_output(content, key):
    try:
        # Remove prefix and suffix
        cleaned_response = clean_response(content)
        # Parse JSON response
        response_data = parse_json_response(cleaned_response)
        # Process content with LaTeX formatting
        bot_response = process_content(response_data.get(key, ""))
        return bot_response
    except Exception as e:
        print(f"Error parsing output: {e}")
        return "..."


def parse_yaml(yaml_string: str) -> dict:
    try:
        data = yaml_string.replace("```yaml", "").replace("```", "")
        data = yaml.safe_load(data)
        
        return data
    except yaml.YAMLError as e:
        print(f"Error parsing YAML: {e}")
        return {}

def load_yaml(yaml_path: str):
    with open(yaml_path, "r") as f:
        yaml_data = parse_yaml(f.read())
    return yaml_data

def save_yaml(yaml_path: str, yaml_data: dict):
    """Saves a YAML dictionary to a file, using a style similar to 'folded block' (>)
    for multi-line strings where newlines are preserved, mimicking the format
    observed in files like meta_agents.yaml.
    """
    # Dump the YAML data using literal block style for multi-line strings
    # This ensures all newlines within the strings are preserved.
    literal_yaml_string = yaml.dump(
        yaml_data,
        indent=2,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,  # Use block style for collections
        default_style='|'          # Use literal style for scalars (preserves newlines)
    )

    # Replace the literal block style indicator ": |" with ": >"
    # This changes the visual marker to '>' while keeping the newline preservation
    # achieved by the literal style dump.
    processed_string = re.sub(r'(:\s*)\|', r'\1>', literal_yaml_string)
    
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(processed_string)


def select_talker(evaluation_results, lambda_weight=0.5):
    evaluated_results = []
    for result in evaluation_results:
        agent_name = result['name']
        internal_scores = result.get('internal_score')
        external_scores = result.get('external_score')
        if internal_scores and external_scores:
            internal_s = internal_scores
            external_s = external_scores
            final_s = ((1 - lambda_weight) * internal_s + lambda_weight * external_s) + random.uniform(-0.01, 0.01)
            evaluated_results.append({**result, "internal_score": internal_s, "external_score": external_s, "final_score": final_s})
    if not evaluated_results:
        return None
    else:
        evaluated_results.sort(key=lambda x: x["final_score"], reverse=True)
        selected_agent_result = evaluated_results[0]
        return selected_agent_result["name"]
  
def create_agent_config(participants_path, meta_agents_path, output_path):
    '''
    Create agent config from participants and meta agents to output file: agents.yaml cause crewai only support agents.yaml.
    '''
    with open(participants_path, "r") as f:
        participants_config = parse_yaml(f.read())

    with open(meta_agents_path, "r") as f:
        meta_agents_config = parse_yaml(f.read())
    combined_agents_config = {**participants_config, **meta_agents_config}

    with open(output_path, "w") as f:
        yaml.dump(combined_agents_config, f, indent=2, sort_keys=False, allow_unicode=True)
        
def dummy_llm_call(data_type):
    if data_type == "yaml":
        return "```yaml\nHello: world!\n```"
    elif data_type == "json":
        return "```json\n{\"Hello\": \"world!\"}\n```"
    elif data_type == "dict":
        return {"Hello": "world!"}
    elif data_type == "list":
        return ["Hello", "world!"]
    else:
        return "Hello, world!"

