import json
# import google.generativeai as genai # 실제 API 사용 시 주석 해제

# --------------------------------------------------------------------------
# ★ LLM 프롬프트 엔지니어링 영역 ★
# --------------------------------------------------------------------------
# LLM의 역할과 출력 형식을 명확하게 지시하는 것이 핵심입니다.
SYSTEM_PROMPT = """
You are an expert HR professional specializing in analyzing IT job postings.
Analyze the given job posting text and extract the key information for each item in the JSON format below.

Rules:
- If there is no content for an item, use an empty string ("") as the value.
- The result must be a valid JSON format. Return only the JSON object without any other explanations.
- For 'qualifications' and 'preferred_qualifications', maintain the bullet point style as much as possible, separating lines with a newline character (\\n).

{
  "job_description": "string",
  "qualifications": "string",
  "preferred_qualifications": "string",
  "hiring_process": "string",
  "benefits": "string"
}
"""

def parse_job_details_with_llm(raw_text: str) -> dict:
    """
    Uses an LLM to extract structured data from a job posting text.
    """
    print("--- Calling LLM Parser ---")
    
    # --- [For Actual Implementation] ---
    # This is where you would call the actual Generative AI API.
    # Example:
    # try:
    #     genai.configure(api_key="YOUR_API_KEY")
    #     model = genai.GenerativeModel('gemini-pro')
    #     response = model.generate_content([SYSTEM_PROMPT, raw_text])
    #     llm_output = response.text
    # except Exception as e:
    #     print(f"LLM API call failed: {e}")
    #     return {}
    # ----------------------------------

    # --- [For Testing with Mock Data] ---
    # This section generates a fake response for testing without calling the actual API.
    # This should be replaced with the actual API call code above.
    print("Using Mock LLM Data for testing...")
    llm_output = """
    ```json
    {
      "job_description": "- Development and operation of the recruitment platform backend system\\n- Design and implementation of new service APIs",
      "qualifications": "- 3+ years of experience with Python, Django/Flask frameworks\\n- Experience with RDBMS (MySQL, MariaDB, etc.)\\n- Experience with Git-based collaboration",
      "preferred_qualifications": "- Experience developing high-traffic services\\n- Experience in a MSA environment\\n- Experience with Docker, Kubernetes",
      "hiring_process": "Document Screening > Coding Test > 1st Technical Interview > 2nd Executive Interview > Final Offer",
      "benefits": "Industry-leading salary, flexible work hours, unlimited vacation, high-end equipment support"
    }
    

