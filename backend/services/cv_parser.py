"""
CV Parser Service - Use LLM to extract structured data from CV text
"""
import json
import os
import re

from openai import OpenAI

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

CV_PARSE_PROMPT = """Bạn là một AI chuyên phân tích CV (Resume). 
Hãy đọc nội dung CV sau và extract thông tin thành JSON có cấu trúc.

CV TEXT:
{cv_text}

Hãy trả về JSON với format sau (không thêm markdown, chỉ JSON thuần):
{{
  "name": "Họ tên đầy đủ",
  "email": "email@example.com hoặc null nếu không có",
  "phone": "số điện thoại hoặc null",
  "location": "địa chỉ hoặc null",
  "summary": "tóm tắt ngắn về ứng viên (1-3 câu)",
  "skills": ["skill1", "skill2", ...],
  "education": [
    {{
      "degree": "Bằng cấp (Cử nhân, Thạc sĩ, ...)",
      "major": "Chuyên ngành",
      "school": "Tên trường",
      "year": "Năm tốt nghiệp hoặc dự kiến tốt nghiệp",
      "gpa": "GPA nếu có, null nếu không"
    }}
  ],
  "experience": [
    {{
      "title": "Chức danh / vị trí",
      "company": "Tên công ty / tổ chức",
      "duration": "Thời gian làm việc (VD: 06/2023 - 12/2023)",
      "description": "Mô tả công việc và thành tích"
    }}
  ],
  "projects": [
    {{
      "name": "Tên dự án",
      "description": "Mô tả dự án",
      "technologies": ["tech1", "tech2"]
    }}
  ],
  "certifications": ["chứng chỉ 1", "chứng chỉ 2"],
  "languages": ["Tiếng Việt", "Tiếng Anh - B2", ...],
  "total_experience_years": 0.5
}}

Lưu ý:
- skills phải là mảng các chuỗi riêng lẻ (Python, SQL, Docker, React, ...)
- Nếu không tìm thấy thông tin, dùng [] cho mảng, null cho string/number
- total_experience_years là tổng số năm kinh nghiệm làm việc (không tính internship ngắn)
- Chỉ trả về JSON, không giải thích thêm"""


def get_llm_client():
    """Get OpenRouter client."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "Không tìm thấy OPENROUTER_API_KEY. "
            "Vui lòng kiểm tra file .env"
        )
    return "openrouter", OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
    )


def parse_cv_with_llm(cv_text: str) -> dict:
    """
    Use LLM to parse CV text into structured data.

    Args:
        cv_text: Raw text extracted from PDF

    Returns:
        Structured CV data as dict
    """
    provider, client = get_llm_client()
    model = os.getenv("DEFAULT_MODEL", "google/gemini-flash-1.5")

    prompt = CV_PARSE_PROMPT.format(cv_text=cv_text[:6000])  # Giới hạn token

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Bạn là AI phân tích CV chuyên nghiệp. Luôn trả về JSON hợp lệ."
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
        extra_headers={
            "HTTP-Referer": "https://student-portal.local",
            "X-Title": "Student Portal CV Parser",
        },
    )
    raw = response.choices[0].message.content

    # Parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Thử extract JSON từ trong response
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise ValueError(f"LLM trả về format không hợp lệ: {raw[:200]}")

    return data
