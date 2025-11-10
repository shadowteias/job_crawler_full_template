import scrapy
import mariadb
from dotenv import load_dotenv
import os
import re

# [수정] 새로 만든 LLM 파서를 import 합니다.
from api.llm_parser import parse_job_details_with_llm

load_dotenv()

class JobCollectorSpider(scrapy.Spider):
    name = 'job_collector'

    def __init__(self, company_id=None, company_name=None, recruits_url=None, *args, **kwargs):
        super(JobCollectorSpider, self).__init__(*args, **kwargs)
        
        if not all([company_id, company_name, recruits_url]):
            raise ValueError("company_id, company_name, recruits_url 인자가 모두 필요합니다.")
        
        self.company_id = company_id
        self.company_name = company_name
        self.start_urls = [recruits_url]
        
        self.db_connection = None
        self.cursor = None
        try:
            self.db_connection = mariadb.connect(
                host=os.getenv('DB_HOST'), user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'), database=os.getenv('DB_NAME'),
                port=int(os.getenv('DB_PORT'))
            )
            self.cursor = self.db_connection.cursor()
            self.logger.info(f"✅ [{self.company_name}] DB 연결 성공")
        except mariadb.Error as err:
            self.logger.error(f"❌ [{self.company_name}] DB 연결 오류: {err}")

    def parse(self, response):
        """
        [핵심 수정] 이제 이 함수는 '목록'과 '상세'를 구분하지 않고,
        모든 유효한 링크를 상세 페이지로 간주하고 `parse_job_details`를 호출합니다.
        '목록' 페이지 판단 로직은 `discover_careers`에서 담당해야 합니다.
        """
        self.logger.info(f"[{self.company_name}] 채용 페이지 분석 시작: {response.url}")

        # 페이지 내의 모든 링크를 수집하여 상세 페이지로 간주하고 크롤링
        links = response.css('a::attr(href)').getall()
        for href in links:
            if href and not href.startswith(('javascript:', '#', 'mailto:')):
                yield response.follow(href, self.parse_job_details)
        
        # 현재 페이지 자체도 상세 페이지일 수 있으므로 함께 처리
        yield from self.parse_job_details(response)


    def parse_job_details(self, response):
        """[핵심 수정] 개별 공고 상세 페이지에서 텍스트를 추출하고 LLM 파서에게 넘깁니다."""
        # 중복 처리를 위해 이미 방문한 URL은 건너뜁니다.
        if not hasattr(self, 'visited_urls'):
            self.visited_urls = set()
        if response.url in self.visited_urls:
            return
        self.visited_urls.add(response.url)
        
        self.logger.info(f"[{self.company_name}] 상세 정보 추출 시도: {response.url}")

        title = response.css('title::text').get() or response.css('h1::text').get() or response.css('h2::text').get()
        title = title.strip() if title else None

        # 제목이 없거나 너무 일반적인 단어이면 유효한 공고가 아니라고 판단
        if not title or title.lower() in ['error', 'not found', '404']:
            return

        # 페이지의 주요 컨텐츠 영역을 최대한 넓게 잡습니다.
        main_content = response.css('main, article, #content, .content, #main-content, .main-content, body')
        full_text = " ".join(main_content.css('*::text').getall())
        full_text = re.sub(r'\s+', ' ', full_text).strip()

        # 텍스트가 너무 짧으면 유효한 공고가 아니라고 판단
        if len(full_text) < 100:
            return

        # LLM 파서를 호출하여 구조화된 데이터 받기
        final_data = parse_job_details_with_llm(full_text)

        # LLM 파싱에 실패했거나 결과가 없으면 아무 작업도 하지 않음
        if not final_data:
            self.logger.warning(f"[{self.company_name}] LLM 분석 실패. 이 공고를 건너뜁니다: {title}")
            return

        try:
            sql = """
            INSERT INTO job_postings (
                company_id, title, post_url, job_description, qualifications,
                preferred_qualifications, hiring_process, benefits, status, crawled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', NOW())
            ON DUPLICATE KEY UPDATE 
                title = VALUES(title), job_description = VALUES(job_description),
                qualifications = VALUES(qualifications), preferred_qualifications = VALUES(preferred_qualifications),
                hiring_process = VALUES(hiring_process), benefits = VALUES(benefits),
                status = 'active', crawled_at = NOW()
            """
            values = (
                self.company_id, title, response.url,
                final_data.get('job_description'), final_data.get('qualifications'),
                final_data.get('preferred_qualifications'), final_data.get('hiring_process'),
                final_data.get('benefits')
            )
            
            self.cursor.execute(sql, values)
            self.db_connection.commit()
            self.logger.info(f"✅ [{self.company_name}] 공고 저장/업데이트 성공: {title}")

        except Exception as e:
            self.logger.error(f"❌ [{self.company_name}] DB 저장 중 에러 발생: {e}")


    def closed(self, reason):
        if self.db_connection:
            if self.cursor:
                self.cursor.close()
            self.db_connection.close()
            self.logger.info(f"[{self.company_name}] DB 연결 종료")
