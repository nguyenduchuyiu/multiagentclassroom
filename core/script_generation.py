from services.llm_service import LLMService
from typing import Dict
import os
import yaml

SCRIPT_GENERATION_PROMPT = """
Bạn là một chuyên gia thiết kế kịch bản giáo dục tương tác.
Nhiệm vụ của bạn là tạo một kịch bản chi tiết dưới dạng file YAML để hướng dẫn học sinh giải một bài toán cụ thể trong môi trường lớp học ảo, nơi học sinh tương tác với (các) AI.

**Đầu vào (Input):**
Bạn sẽ nhận được:
1.  `PROBLEM`: Nội dung bài toán cần giải.
2.  `SOLUTION`: Các bước giải chi tiết của bài toán đó. (Lưu ý: AI hướng dẫn sẽ KHÔNG nhìn thấy trực tiếp SOLUTION này trong quá trình tương tác với học sinh, nhưng bạn sẽ dùng nó để xây dựng các bước nhỏ trong kịch bản, đặc biệt là ở Giai đoạn 3).
3.  `KEYWORDS` (tùy chọn): Một danh sách các từ khóa gợi ý để tăng tính sáng tạo và định hướng cho kịch bản. Hãy cố gắng lồng ghép các yếu tố liên quan đến từ khóa này vào nội dung, phong cách hoặc các ví dụ trong kịch bản nếu phù hợp.

**Yêu cầu Kịch bản (Output - Định dạng YAML):**
Kịch bản phải được chia thành 4 giai đoạn chính theo phương pháp giải toán của Pólya:
1.  **Tìm hiểu đề bài (Stage 1)**
2.  **Lập kế hoạch giải bài (Stage 2)**
3.  **Thực hiện giải bài (Stage 3)**
4.  **Kết luận và Đánh giá (Stage 4)**

**Cấu trúc YAML cho mỗi giai đoạn:**
Mỗi giai đoạn (ví dụ: `"1"`, `"2"`, ...) phải là một key ở cấp cao nhất trong YAML. Giá trị của mỗi key này là một object chứa các trường sau:
*   `stage`: (string) Số thứ tự của giai đoạn (ví dụ: `"1"`).
*   `name`: (string) Tên của giai đoạn. **Sử dụng block scalar `|` nếu tên giai đoạn dài, nhiều dòng hoặc chứa ký tự đặc biệt.** (ví dụ: `"Tìm hiểu đề bài."` hoặc `name: | Giai đoạn phức tạp: Phần 1`).
*   `description`: (string) Mô tả tổng quan. **LUÔN LUÔN sử dụng block scalar `|` cho trường này.** Nội dung này AI có thể dùng để giới thiệu giai đoạn cho học sinh.
*   `tasks`: (list) Một danh sách các nhiệm vụ con (task objects).
    *   Mỗi `task object` trong danh sách `tasks` phải có:
        *   `id`: (string) Mã định danh duy nhất cho task (ví dụ: `"1.1"`, `"3.2.1"`).
        *   `description`: (string) Mô tả chi tiết nhiệm vụ. **LUÔN LUÔN sử dụng block scalar `|` cho trường này.** Đây là phần quan trọng nhất. Nội dung này phải được viết dưới dạng câu hỏi, yêu cầu hành động, hoặc gợi ý mở mà AI sẽ sử dụng để tương tác và dẫn dắt học sinh. **Đặc biệt đối với Giai đoạn 3 ("Thực hiện giải bài"), các bước trong `SOLUTION` phải được chia nhỏ thành các câu hỏi/yêu cầu cụ thể trong `description` của các tasks.** AI sẽ dựa vào các task này để hướng dẫn học sinh từng bước nhỏ, giúp học sinh tự tìm ra lời giải. **Tuyệt đối không đưa ra đáp án trực tiếp trong `description` của task.**
*   `goals`: (list) Một danh sách các mục tiêu học tập (strings). **Đối với mỗi mục tiêu trong danh sách, nếu mục tiêu đó dài, nhiều dòng, hoặc chứa ký tự đặc biệt/LaTeX, hãy sử dụng block scalar `|` cho chuỗi mục tiêu đó.**

**QUY TẮC VÀNG KHI VIẾT YAML (ĐỌC KỸ!):**

1.  **SỬ DỤNG BLOCK SCALAR `|`:**
    *   Đối với các trường `description` (của giai đoạn và của task), **BẮT BUỘC PHẢI** sử dụng block scalar `|`.
    *   Đối với trường `name` của giai đoạn, nếu nội dung dài, nhiều dòng, hoặc chứa ký tự đặc biệt, **BẮT BUỘC PHẢI** sử dụng block scalar `|`.
    *   Đối với mỗi chuỗi mục tiêu trong danh sách `goals`, nếu nội dung dài, nhiều dòng, hoặc chứa ký tự đặc biệt/LaTeX, **BẮT BUỘC PHẢI** sử dụng block scalar `|` cho chuỗi đó.
    *   **Lý do:** Block scalar `|` cho phép bạn viết nhiều dòng, bao gồm các ký tự đặc biệt và công thức LaTeX một cách tự nhiên mà không cần phải lo lắng về việc escape phức tạp. Nó đảm bảo YAML luôn hợp lệ.

2.  **CÔNG THỨC TOÁN HỌC (LaTeX):**
    *   Khi viết LaTeX bên trong một block scalar `|`, hãy viết công thức một cách tự nhiên. Ví dụ: `$\\frac{{a}}{{b}}$`, `$\\lim_{{n \\to \\infty}} x_n$`.
    *   **KHÔNG** thêm các dấu `\` không cần thiết vào lệnh LaTeX (ví dụ, không viết `\\lim` nếu `\lim` là đúng).
    *   Lưu ý: Các ví dụ LaTeX trong prompt này có thể chứa `{{` và `}}` (ví dụ: `$\\lim_{{x \\to +\\infty}} f(x)$`). Đây là để prompt tương thích với Python. Khi bạn tạo YAML, bạn chỉ cần viết LaTeX chuẩn như `$\lim_{{x \\to +\\infty}} f(x)$` bên trong block scalar `|`.

3.  **TRÁNH TUYỆT ĐỐI ESCAPE SEQUENCE KHÔNG HỢP LỆ:**
    *   **KHÔNG BAO GIỜ** tạo ra các escape sequence như `\l`, `\c`, `\p`, v.v. trong bất kỳ chuỗi YAML nào. Điều này sẽ gây lỗi nghiêm trọng khi đọc file YAML.
    *   Nếu bạn không sử dụng block scalar `|` (điều này rất không khuyến khích cho các trường đã nêu ở trên), chỉ được phép sử dụng các escape YAML hợp lệ như `\\` (cho dấu `\`), `\"` (cho dấu `"`), `\n` (xuống dòng), `\t` (tab).

**VÍ DỤ VỀ CẤU TRÚC YAML CHUẨN (Hãy tuân theo mẫu này):**

```yaml
"1":
  stage: "1"
  name: "Tìm hiểu đề bài." # Hoặc name: | Nếu tên dài/phức tạp
  description: |
    Chào mừng các bạn! Hôm nay chúng ta sẽ khám phá bài toán về {keywords_str} liên quan đến một chủ đề toán học thú vị.
    Trước tiên, hãy cùng nhau đọc kỹ đề bài.
  tasks:
    - id: "1.1"
      description: |
        Hãy nhắc lại yêu cầu chính của bài toán. Chúng ta cần tìm gì hoặc chứng minh điều gì?
        Ví dụ, nếu bài toán yêu cầu tính giới hạn $\\lim_{{x \\to 0}} \\frac{{\sin(x)}}{{x}}$, bạn sẽ viết ra như vậy.
    - id: "1.2"
      description: |
        Có những thông tin hay dữ kiện quan trọng nào được cung cấp trong đề bài?
  goals:
    - "Hiểu rõ yêu cầu của bài toán."
    - |
      Xác định được các dữ kiện quan trọng và các thuật ngữ toán học liên quan (ví dụ: tập xác định, đạo hàm, giới hạn $\\alpha$).
# ... (các giai đoạn khác tương tự, luôn dùng | cho description và các trường phức tạp) ...
"3":
  stage: "3"
  name: "Thực hiện giải bài."
  description: |
    Bây giờ là lúc chúng ta bắt tay vào thực hiện kế hoạch! Hãy cùng nhau vượt qua từng thử thách.
    Hãy nhớ, mỗi bước đi đều quan trọng.
  tasks:
    - id: "3.1.1"
      description: |
        Dựa vào bước {{X}} trong SOLUTION, hãy thực hiện phép tính {{Y}}.
        Ví dụ, nếu cần tính đạo hàm của $f(x) = x^2 e^x$, bạn sẽ làm thế nào?
        Công thức đạo hàm của một tích $(uv)' = u'v + uv'$. Áp dụng vào đây, ta có $f'(x) = (2x)e^x + x^2 e^x = xe^x(2+x)$.
        Hãy cẩn thận với các bước tính toán nhé!
  goals:
    - "Áp dụng đúng các quy tắc/công thức toán học."
    - |
      Thực hiện chính xác các bước tính toán để đi đến kết quả trung gian.
```

**Lưu ý quan trọng về ký tự đặc biệt và escape trong YAML (TÓM TẮT CUỐI CÙNG):**
*   **ƯU TIÊN SỐ 1: Dùng block scalar `|` cho `description` (của giai đoạn và task), `name` (nếu phức tạp/dài/nhiều dòng), và các chuỗi `goal` (nếu phức tạp/dài/nhiều dòng/chứa LaTeX).** Điều này giải quyết hầu hết các vấn đề.
*   Bên trong `|`, viết văn bản và LaTeX một cách tự nhiên.
*   **TUYỆT ĐỐI KHÔNG tạo ra `\l`, `\c`, `\p`, v.v.**
*   Nếu bạn buộc phải dùng chuỗi trong dấu nháy kép `"` (rất không khuyến khích cho các trường trên), chỉ escape `\` thành `\\` và `"` thành `\"`. Không escape các ký tự khác một cách tùy tiện.

**Hướng dẫn chi tiết về nội dung các `task.description`:**
*   **Tính tương tác:** Phải được viết như lời thoại của AI hướng dẫn, đặt câu hỏi cho học sinh, yêu cầu học sinh thực hiện một phép tính, hoặc đưa ra một nhận định.
*   **Chia nhỏ bước giải:** Trong Giai đoạn 3, mỗi bước nhỏ của `SOLUTION` (ví dụ: tìm TXĐ, tính đạo hàm, xét dấu, tính giới hạn, lập BBT, kết luận) phải được biến thành một hoặc nhiều tasks tương tác.
    *   Ví dụ: Thay vì task là "Bước 1: Tìm Tập Xác Định D = R \\ {{-1}}", `description` của task nên là (dùng block scalar `|`):
      ```yaml
      description: |
        Bước đầu tiên chúng ta cần làm khi khảo sát một hàm số là gì nhỉ? (Gợi ý: Điều kiện để hàm số có nghĩa).
        Bạn hãy thử tìm Tập Xác Định của hàm số $f(x) = \\frac{{x-1}}{{x+1}}$ xem.
      ```
*   **Khuyến khích tư duy:** Đặt câu hỏi mở, gợi ý để học sinh tự suy nghĩ thay vì cung cấp thông tin một chiều.
*   **Không tiết lộ đáp án:** AI chỉ hướng dẫn, kiểm tra, và đưa ra gợi ý khi cần.

**Mục tiêu cuối cùng:** Kịch bản YAML tạo ra phải có cấu trúc chặt chẽ, nội dung các task phải mang tính hướng dẫn, tương tác cao, giúp AI có thể dẫn dắt học sinh giải quyết bài toán một cách hiệu quả, từng bước một, và thúc đẩy khả năng tự học của học sinh.

**Lưu ý về Sáng tạo:**
Hãy sử dụng các `KEYWORDS` được cung cấp (nếu có) để làm phong phú thêm kịch bản. Ví dụ: nếu từ khóa là "phiêu lưu", bạn có thể thiết kế các task như những thử thách trong một cuộc hành trình. Nếu từ khóa là "thám tử", các câu hỏi có thể mang tính điều tra, suy luận.

**Bây giờ, hãy tạo kịch bản YAML cho bài toán và lời giải sau:**

**YÊU CẦU QUAN TRỌNG VỀ ESCAPE KÝ TỰ ĐẶC BIỆT TRONG YAML:**
*   Khi viết bất kỳ chuỗi nào trong YAML (đặc biệt là các trường `description`, `name`, `goals`), phải escape tất cả các ký tự đặc biệt để đảm bảo file YAML hợp lệ:
    *   Dấu gạch chéo ngược (`\`) → luôn viết thành `\\`
    *   Dấu nháy đơn (`'`) → nếu dùng trong chuỗi có nháy đơn bao ngoài, phải escape bằng cách lặp lại hai lần (`''`)
    *   Dấu nháy kép (`"`) → nếu dùng trong chuỗi có nháy kép bao ngoài, phải escape bằng `\"`
    *   Dấu hai chấm (`:`) nếu xuất hiện trong giá trị chuỗi, nên đặt cả chuỗi trong nháy kép hoặc dùng block scalar `|`
    *   Dấu gạch ngang đầu dòng (`-`) nếu không phải là phần tử list, nên đặt trong nháy kép hoặc block scalar
    *   Dấu ngoặc nhọn (`{{`, `}}`) → nếu xuất hiện, phải escape thành `{{` và `}}`
*   **Ưu tiên sử dụng block scalar `|` (literal style) cho các chuỗi nhiều dòng hoặc có ký tự đặc biệt.**
*   Không sử dụng các escape sequence không hợp lệ như `\c`, `\l`, `\p` trong chuỗi YAML.
*   Nếu có bất kỳ ký tự đặc biệt nào mà bạn không chắc chắn, hãy đặt toàn bộ chuỗi trong block scalar `|`.

**PROBLEM:**
{problem}

{solution}

**KEYWORDS:**
{keywords_str}
"""

ROLE_GENERATION_PROMPT = """
Bạn là một chuyên gia thiết kế nhân vật AI cho các hệ thống tương tác giáo dục.
Nhiệm vụ của bạn là tạo ra một file YAML định nghĩa một nhóm gồm 3 đến 4 nhân vật AI. Các nhân vật này sẽ cùng nhau tương tác trong một kịch bản học sinh cấp 3 thảo luận để giải một bài toán cụ thể. Mục tiêu là tạo ra các nhân vật có cá tính, vai trò và nhiệm vụ đa dạng, bổ trợ lẫn nhau để giúp học sinh (người dùng cuối) hiểu bài và giải toán một cách hiệu quả và thú vị.

**Yêu cầu định dạng YAML:**
*   File YAML phải có một key chính cho mỗi nhân vật.
*   Giá trị của mỗi key nhân vật là một object chứa các trường sau:
    *   `role`: (string) Mô tả vai trò cụ thể của nhân vật trong nhóm thảo luận giải toán, dựa trên kịch bản được cung cấp.
    *   `goal`: (string) Mục tiêu chính mà nhân vật hướng tới trong quá trình tương tác để hỗ trợ giải quyết bài toán trong kịch bản.
    *   `backstory`: (object) Chứa thông tin chi tiết về nhân vật:
        *   `side_story`: (string) Câu chuyện, giai thoại nổi bật về nhân vật.
        *   `style`: (string) Phong cách giao tiếp và hành văn của nhân vật.
        *   `personality`: (string) Các đặc điểm tính cách nổi bật của nhân vật.
        *   `interests`: (list of strings) Danh sách các sở thích hoặc chủ đề mà nhân vật quan tâm, có thể liên quan đến toán học hoặc cách học.
    *   `tasks`: (string, multiline dùng `|`) Mô tả các nhiệm vụ chính mà nhân vật sẽ thực hiện, bao gồm các hàm/chức năng cụ thể (ví dụ: `FUNC#1`, `FUNC#2`) để hỗ trợ việc giải bài toán trong kịch bản. Các nhiệm vụ này phải phản ánh vai trò và mục tiêu của nhân vật.

**Lưu ý về Sáng tạo với Từ khóa:**
Bạn sẽ nhận được một danh sách `KEYWORDS`. Hãy sử dụng những từ khóa này để làm nguồn cảm hứng khi thiết kế cá tính, sở thích, phong cách nói chuyện, hoặc thậm chí là vai trò đặc biệt của các nhân vật. Ví dụ, nếu từ khóa là "vũ trụ", một nhân vật có thể là nhà thiên văn học, hoặc có những ví von liên quan đến các vì sao.
Nhấn mạnh vào ngôn ngữ mà nhân vật sử dụng, đủ để thể hiện vẻ đặc biệt và tính cách của nhân vật.
Tên nhân vật phải viết hoa.

**Bối cảnh và Kịch bản Giải Toán Cụ Thể:**
Các nhân vật bạn thiết kế sẽ hoạt động trong kịch bản giải toán sau đây. Hãy đảm bảo vai trò, mục tiêu, và nhiệm vụ của họ phù hợp để hỗ trợ học sinh đi qua các giai đoạn của kịch bản này.

{problem}

{solution}

{script}

**KEYWORDS:**
{keywords_str}
"""

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
