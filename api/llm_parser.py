# api/llm_parser.py

import os
from functools import lru_cache

from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline

# 한국어 지원되는 NLI/분류용 모델 (로컬에 다운로드됨)
# 필요하면 환경 변수로 바꿀 수 있게 해둠.
JOB_CLASSIFIER_MODEL = os.getenv(
    "JOB_CLASSIFIER_MODEL",
    "joeddav/xlm-roberta-large-xnli"  # 한국어 포함 멀티링구얼 NLI
)

@lru_cache()
def _get_zero_shot_classifier():
    tokenizer = AutoTokenizer.from_pretrained(JOB_CLASSIFIER_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(JOB_CLASSIFIER_MODEL)
    clf = pipeline(
        "zero-shot-classification",
        model=model,
        tokenizer=tokenizer,
        device=-1,  # CPU, GPU 쓰면 0으로 설정
    )
    return clf


def is_job_posting(text: str, threshold: float = 0.65) -> bool:
    """
    주어진 텍스트가 '채용공고'일 확률이 충분히 높은지 판단.
    GPU 없으면 조금 느릴 수 있지만, 후보 페이지만 넣으므로 감당 가능한 수준.
    """
    if not text:
        return False

    snippet = text[:2000]  # 너무 길면 자르고
    clf = _get_zero_shot_classifier()

    labels = ["채용공고", "채용공고 아님"]
    result = clf(
        snippet,
        candidate_labels=labels,
        hypothesis_template="이 문서는 {}이다.",
    )

    top_label = result["labels"][0]
    top_score = float(result["scores"][0])

    # 디버깅 원하면 로그
    # print(top_label, top_score)

    return (top_label == "채용공고") and (top_score >= threshold)


def parse_job_details_with_llm(text: str, url: str = "", company_name: str = "") -> dict:
    """
    선택: 상세 필드 추출용 LLM.
    지금은 placeholder로 두고, 나중에 온프레 LLM/파인튜닝 모델 붙일 때 구현.

    반환 형식 예:
    {
        "job_description": "...",
        "qualifications": "...",
        "preferred_qualifications": "...",
        "hiring_process": "...",
        "benefits": "...",
        "employment_type": "...",
        "salary": "...",
        "location": "...",
    }
    """
    # 현재는 규칙 기반 파서가 있기 때문에 여기서는 빈 dict 반환
    # 추후 필요 시 구현
    return {}
