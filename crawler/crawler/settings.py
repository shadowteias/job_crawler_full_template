import os
import sys
from pathlib import Path

# -----------------------------------------------------------------------------
# Django 연동 설정
# -----------------------------------------------------------------------------
# 이 settings.py 위치: /app/crawler/crawler/settings.py
# Django 프로젝트 루트: /app  (config/, api/ 가 있는 곳)
DJANGO_BASE_DIR = Path(__file__).resolve().parents[2]  # /app

# /app 을 sys.path 에 추가해서 `import api`, `import config` 가 가능하게 함
if str(DJANGO_BASE_DIR) not in sys.path:
    sys.path.insert(0, str(DJANGO_BASE_DIR))

# Django 설정 모듈 지정
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Django 초기화 (Scrapy에서 Django ORM, 모델, 기타 사용 가능)
import django
django.setup()

# -----------------------------------------------------------------------------
# Scrapy 기본 설정
# -----------------------------------------------------------------------------

BOT_NAME = "crawler"

SPIDER_MODULES = ["crawler.spiders"]
NEWSPIDER_MODULE = "crawler.spiders"

# 로봇 배제 규약: 크롤링 정책에 맞게 조정 (개발용이라면 False 유지)
ROBOTSTXT_OBEY = False

# 너무 과격하게 쏘지 않도록 딜레이 (필요 시 조절)
DOWNLOAD_DELAY = 0.5

# 동시 요청 수 등은 기본값 사용 (필요하면 아래 주석 해제)
# CONCURRENT_REQUESTS = 8

DEFAULT_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

# 로그 레벨 (개발 중이면 'INFO' 또는 'DEBUG')
LOG_LEVEL = "INFO"
