# # 논리적 추론 기반 코드 메모용으로 유지

# import scrapy
# from urllib.parse import urlparse
# import mariadb  # import 변경 (mysql.connector -> mariadb)
# from dotenv import load_dotenv
# import os

# load_dotenv()

# class DiscoverCareersSpider(scrapy.Spider):
#     name = 'discover_careers'

#     # --- 설정 값 ---
#     # 1. 따라갈 링크를 찾기 위한 키워드
#     FOLLOW_LINK_KEYWORDS = ['채용', '인재', '공고', 'career', 'recruit', 'job', 'hire']
    
#     # 2. 현재 페이지가 '채용 목록' 페이지인지 판단하기 위한 키워드
#     #    (이런 단어가 포함된 링크가 여러 개 있으면 목록 페이지로 간주)
#     JOB_LIST_KEYWORDS = ['상세', '보기', '지원', 'view', 'detail', 'more', 'apply']
    
#     # 3. '채용 목록' 페이지로 판단할 최소 링크 개수
#     JOB_LIST_THRESHOLD = 3

#     # 4. 최대 탐색 깊이
#     MAX_DEPTH = 3

#     def __init__(self, company_name=None, homepage_url=None, *args, **kwargs):
#         super(DiscoverCareersSpider, self).__init__(*args, **kwargs)
#         if not company_name or not homepage_url:
#             raise ValueError("company_name과 homepage_url 인자가 필요합니다.")
            
#         self.company_name = company_name
#         self.start_urls = [homepage_url]
#         self.visited_urls = set()
#         self.found = False

#         self.db_connection = None
#         self.cursor = None
#         try:
#             self.db_connection = mariadb.connect(
#                 host=os.getenv('DB_HOST'),
#                 user=os.getenv('DB_USER'),
#                 password=os.getenv('DB_PASSWORD'),
#                 database=os.getenv('DB_NAME'),
#                 port=int(os.getenv('DB_PORT'))
#             )
#             self.cursor = self.db_connection.cursor()
#         except mariadb.Error as err:
#             self.logger.error(f"❌ [{self.company_name}] DB 연결 오류: {err}")

#     def start_requests(self):
#         for url in self.start_urls:
#             # meta 정보에 현재 탐색 깊이(depth)를 기록하며 시작
#             yield scrapy.Request(url, callback=self.parse, meta={'depth': 1})

#     def parse(self, response):
#         # 이미 확정 페이지를 찾았다면, 더 이상 아무 작업도 하지 않음
#         if self.found:
#             return

#         current_url = response.url
#         current_depth = response.meta['depth']
#         self.visited_urls.add(current_url)
#         self.logger.info(f"[{self.company_name}][깊이:{current_depth}] 페이지 탐색 중: {current_url}")

#         # --- [핵심 로직 1] 현재 페이지가 '채용 목록' 페이지인지 판단 ---
#         job_list_link_count = 0
#         all_links = response.css('a')
#         for link in all_links:
#             link_text = "".join(link.css('::text').getall()).lower().strip()
#             if any(keyword in link_text for keyword in self.JOB_LIST_KEYWORDS):
#                 job_list_link_count += 1

#         # '상세보기' 같은 링크가 3개 이상 발견되면, 여기를 최종 목적지로 확정!
#         if job_list_link_count >= self.JOB_LIST_THRESHOLD:
#             self.logger.info(f"✅ [{self.company_name}] 최종 채용 페이지 발견! URL: {current_url}")
#             self.save_url_to_db(current_url)
#             self.found = True # 플래그를 True로 설정하여 모든 추가 탐색을 중단
#             return # 여기서 탐색 종료

#         # --- [핵심 로직 2] 아직 목적지가 아니라면, 다음 탐색할 링크 찾기 ---
#         if current_depth < self.MAX_DEPTH:
#             next_links_to_follow = []
#             for link in all_links:
#                 link_href = link.css('::attr(href)').get()
#                 link_text = "".join(link.css('::text').getall()).lower().strip()

#                 if not link_href or link_href.startswith(('#', 'javascript:', 'mailto:')):
#                     continue

#                 # 링크 텍스트나 URL 자체에 '채용' 관련 키워드가 있는지 확인
#                 if any(keyword in link_text or keyword in link_href.lower() for keyword in self.FOLLOW_LINK_KEYWORDS):
#                     next_url = response.urljoin(link_href)
#                     if next_url not in self.visited_urls:
#                         # 중복을 피하기 위해 방문한 적 없는 URL만 후보에 추가
#                         if next_url not in next_links_to_follow:
#                             next_links_to_follow.append(next_url)
            
#             # 찾은 후보 링크들로 다음 탐색을 요청
#             for url in next_links_to_follow:
#                 yield scrapy.Request(url, callback=self.parse, meta={'depth': current_depth + 1})

#     def save_url_to_db(self, url):
#         if not self.cursor:
#             self.logger.error("DB 커서가 없어 저장할 수 없습니다.")
#             return
#         try:
#             # 점수 시스템 대신, 'CONFIRMED' 상태로 URL을 확정하여 저장
#             sql = """
#             UPDATE companies 
#             SET recruits_url = %s, 
#                 recruits_url_status = 'CONFIRMED', 
#                 recruits_url_score = 100 
#             WHERE name = %s
#             """
#             self.cursor.execute(sql, (url, self.company_name))
#             self.db_connection.commit()
#             self.logger.info(f"✅ [{self.company_name}] DB에 채용 페이지 URL 저장 완료.")
#         except Exception as e:
#             self.logger.error(f"❌ [{self.company_name}] DB 저장 중 에러: {e}")

#     def closed(self, reason):
#         if not self.found:
#             self.logger.warning(f"⚠️ [{self.company_name}] 탐색을 마쳤지만 최종 채용 페이지를 확정하지 못했습니다.")
#         if self.db_connection:
#             if self.cursor:
#                 self.cursor.close()
#             self.db_connection.close()
#             self.logger.info(f"[{self.company_name}] DB 연결 종료됨. 이유: {reason}")



# #버전2: 6/15

# # 파일명: crawler/spiders/discover_careers.py
# # 이 코드로 기존 파일의 내용을 완전히 덮어쓰세요.

# import scrapy
# from urllib.parse import urlparse, urljoin
# import mariadb
# from dotenv import load_dotenv
# import os
# import re

# load_dotenv()

# class DiscoverCareersSpider(scrapy.Spider):
#     name = 'discover_careers'

#     PRIORITY_KEYWORDS = [
#         '채용공고', '채용', '채용안내', '채용정보', 
#         '채용사이트가기', '채용사이트', 'career', 'recruit', 'employment'
#     ]
#     MAX_DEPTH = 5

#     def __init__(self, company_name=None, homepage_url=None, *args, **kwargs):
#         super(DiscoverCareersSpider, self).__init__(*args, **kwargs)
#         if not company_name or not homepage_url:
#             raise ValueError("company_name과 homepage_url 인자가 필요합니다.")
            
#         self.company_name = company_name
#         self.start_urls = [homepage_url]
#         self.found_url = None
#         self.visited_urls = set()

#         self.db_connection = None
#         self.cursor = None
#         try:
#             self.db_connection = mariadb.connect(
#                 host=os.getenv('DB_HOST'), user=os.getenv('DB_USER'),
#                 password=os.getenv('DB_PASSWORD'), database=os.getenv('DB_NAME'),
#                 port=int(os.getenv('DB_PORT'))
#             )
#             self.cursor = self.db_connection.cursor()
#         except mariadb.Error as err:
#             self.logger.error(f"❌ [{self.company_name}] DB 연결 오류: {err}")

#     def start_requests(self):
#         for url in self.start_urls:
#             # meta에 'previous_links'를 빈 set으로 초기화하여 전달
#             yield scrapy.Request(url, callback=self.parse_navigation, meta={'depth': 1, 'previous_links': set()})

#     def normalize_text(self, text):
#         return re.sub(r'\s+', '', text).lower().strip()

#     def parse_navigation(self, response):
#         if self.found_url: return

#         current_url = response.url
#         if current_url in self.visited_urls: return
#         self.visited_urls.add(current_url)

#         current_depth = response.meta['depth']
#         # [핵심 변경] 이전 페이지에서 전달받은 링크 목록을 가져옴
#         previous_links = response.meta.get('previous_links', set())

#         self.logger.info(f"[{self.company_name}][깊이:{current_depth}] ----------------------------------------------------")
#         self.logger.info(f"[{self.company_name}][깊이:{current_depth}] 탐색 시작: {current_url}")
#         self.logger.info(f"[{self.company_name}][깊이:{current_depth}] ----------------------------------------------------")


#         found_links_on_this_page = []
        
#         self.logger.info(f"[{self.company_name}] 페이지 내 모든 링크 분석 시작...")
#         all_links = response.css('a')
#         if not all_links:
#             self.logger.warning(f"[{self.company_name}] 이 페이지에서 <a> 태그를 찾을 수 없습니다. (자바스크립트 렌더링 의심)")

#         for link in all_links:
#             href = link.css('::attr(href)').get()
#             raw_text = "".join(link.css('::text').getall())
#             normalized_text = self.normalize_text(raw_text)
            
#             log_msg = f"  - 발견된 링크: '{raw_text.strip()}' | 정규화: '{normalized_text}' | Href: '{href}'"

#             if not href or not normalized_text or href.startswith(('#', 'javascript:')):
#                 continue

#             match_status = "[불일치]"
#             if normalized_text in self.PRIORITY_KEYWORDS:
#                 priority = self.PRIORITY_KEYWORDS.index(normalized_text)
#                 full_url = response.urljoin(href)
                
#                 # [핵심 변경] 이 페이지에서 찾은 모든 유효 링크를 일단 저장
#                 found_links_on_this_page.append((priority, full_url))
#                 match_status = f"✅[일치! 우선순위: {priority}]"
            
#             self.logger.info(log_msg + f" -> {match_status}")
        
#         # [핵심 변경] 현재 페이지에서 찾은 링크들 중에서, 이전 페이지에도 있었던 링크는 필터링
#         next_candidate_links = []
#         for priority, url in found_links_on_this_page:
#             if url in previous_links:
#                 self.logger.warning(f"  - [필터링됨] 이전 페이지에도 있었던 링크입니다: {url}")
#                 continue
#             next_candidate_links.append((priority, url))

#         self.logger.info(f"[{self.company_name}] 페이지 내 링크 분석 완료. 이전 링크 제외 후 {len(next_candidate_links)}개의 유효 후보 발견.")


#         if next_candidate_links and current_depth < self.MAX_DEPTH:
#             next_candidate_links.sort()
#             highest_priority_url = next_candidate_links[0][1]
            
#             if highest_priority_url not in self.visited_urls:
#                 self.logger.info(f"[{self.company_name}] 우선순위 가장 높은 링크로 이동 결정: {highest_priority_url}")
                
#                 # [핵심 변경] 다음 요청에 '현재 페이지에서 찾은 모든 링크'를 'previous_links'로 전달
#                 current_page_urls_set = {url for _, url in found_links_on_this_page}
                
#                 yield scrapy.Request(
#                     highest_priority_url, 
#                     callback=self.parse_navigation, 
#                     meta={'depth': current_depth + 1, 'previous_links': current_page_urls_set}
#                 )
#                 return

#         self.logger.info(f"[{self.company_name}] 더 이상 따라갈 '새로운' 우선순위 링크가 없어 탐색을 종료합니다.")
#         self.logger.info(f"[{self.company_name}] 현재 페이지를 최종 URL로 확정: {current_url}")
#         self.found_url = current_url

#     def save_url_to_db(self):
#         if not self.found_url:
#             self.logger.warning(f"⚠️ [{self.company_name}] 최종 채용 페이지를 확정하지 못했습니다.")
#             return

#         self.logger.info(f"✅ [{self.company_name}] 최종 채용 페이지 저장! URL: {self.found_url}")
#         if not self.cursor:
#             self.logger.error("DB 커서가 없어 저장할 수 없습니다.")
#             return
#         try:
#             sql = "UPDATE companies SET recruits_url = %s, recruits_url_status = 'CONFIRED' WHERE name = %s"
#             self.cursor.execute(sql, (self.found_url, self.company_name))
#             self.db_connection.commit()
#         except Exception as e:
#             self.logger.error(f"❌ [{self.company_name}] DB 저장 중 에러: {e}")

#     def closed(self, reason):
#         self.save_url_to_db()
#         if self.db_connection:
#             if self.cursor: self.cursor.close()
#             self.db_connection.close()
#             self.logger.info(f"[{self.company_name}] DB 연결 종료됨. 이유: {reason}")





# # 파일명: crawler/spiders/discover_careers.py
# # 이 코드로 기존 파일의 내용을 완전히 덮어쓰세요.

# import scrapy
# from urllib.parse import urlparse, urljoin
# import mariadb
# from dotenv import load_dotenv
# import os
# import json
# import re

# load_dotenv()

# class DiscoverCareersSpider(scrapy.Spider):
#     name = 'discover_careers'

#     # --- 설정 값 ---
#     TARGET_API_KEYWORD = "getMainView"
#     TARGET_MENU_NAME = "채용공고"
#     PRIORITY_KEYWORDS = [
#         '채용공고', '채용', '채용안내', '채용정보', 
#         '채용사이트가기', '채용사이트', 'career', 'recruit', 'employment'
#     ]
#     MAX_DEPTH = 5

#     def __init__(self, company_name=None, homepage_url=None, *args, **kwargs):
#         super(DiscoverCareersSpider, self).__init__(*args, **kwargs)
#         if not company_name or not homepage_url:
#             raise ValueError("company_name과 homepage_url 인자가 필요합니다.")
            
#         self.company_name = company_name
#         self.homepage_url = homepage_url
#         self.found_url = None
#         self.visited_urls = set()

#         # DB 연결
#         self.db_connection = None
#         self.cursor = None
#         try:
#             self.db_connection = mariadb.connect(
#                 host=os.getenv('DB_HOST'), user=os.getenv('DB_USER'),
#                 password=os.getenv('DB_PASSWORD'), database=os.getenv('DB_NAME'),
#                 port=int(os.getenv('DB_PORT'))
#             )
#             self.cursor = self.db_connection.cursor()
#         except mariadb.Error as err:
#             self.logger.error(f"❌ [{self.company_name}] DB 연결 오류: {err}")

#     def start_requests(self):
#         """항상 HTML 우선 탐색(전략 2)부터 시작합니다."""
#         self.logger.info(f"[{self.company_name}] HTML 우선 탐색을 시작합니다: {self.homepage_url}")
#         yield scrapy.Request(
#             self.homepage_url, 
#             callback=self.parse_navigation, 
#             meta={'depth': 1, 'previous_links': set()}
#         )

#     def normalize_text(self, text):
#         return re.sub(r'\s+', '', text).lower().strip()

#     def parse_navigation(self, response):
#         """[핵심] 1. HTML 링크를 먼저 찾고, 없으면 2. API를 시도합니다."""
#         if self.found_url: return
#         current_url = response.url
#         if current_url in self.visited_urls: return
#         self.visited_urls.add(current_url)
#         current_depth = response.meta['depth']
#         previous_links = response.meta.get('previous_links', set())
#         self.logger.info(f"[{self.company_name}][깊이:{current_depth}] HTML 탐색 중: {current_url}")

#         # 1. HTML 우선 탐색
#         found_links_on_this_page = []
#         for link in response.css('a'):
#             href = link.css('::attr(href)').get()
#             normalized_text = self.normalize_text("".join(link.css('::text').getall()))
#             if not href or not normalized_text or href.startswith(('#', 'javascript:')): continue
#             if normalized_text in self.PRIORITY_KEYWORDS:
#                 priority = self.PRIORITY_KEYWORDS.index(normalized_text)
#                 full_url = response.urljoin(href)
#                 found_links_on_this_page.append((priority, full_url))
        
#         next_candidate_links = [link for link in found_links_on_this_page if link[1] not in previous_links]
        
#         if next_candidate_links and current_depth < self.MAX_DEPTH:
#             next_candidate_links.sort()
#             highest_priority_url = next_candidate_links[0][1]
#             if highest_priority_url not in self.visited_urls:
#                 current_page_urls_set = {url for _, url in found_links_on_this_page}
#                 yield scrapy.Request(
#                     highest_priority_url, 
#                     callback=self.parse_navigation, 
#                     meta={'depth': current_depth + 1, 'previous_links': current_page_urls_set}
#                 )
#                 return

#         # 2. HTML 링크가 없다면, 현재 페이지에서 API 탐색 시도
#         self.logger.warning(f"[{self.company_name}] HTML 탐색 후보 없음. 현재 페이지에서 API 탐색 시도...")
#         parsed_uri = urlparse(current_url)
#         base_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}"
#         api_url = urljoin(base_url, f"/appsite/company/{self.TARGET_API_KEYWORD}")
        
#         yield scrapy.Request(
#             api_url,
#             callback=self.parse_api_response,
#             errback=self.handle_api_failure,
#             meta={
#                 'depth': current_depth,
#                 'previous_links': {url for _, url in found_links_on_this_page},
#                 'fallback_url': current_url # API 실패 시 돌아올 URL
#             }
#         )
    
#     def handle_api_failure(self, failure):
#         """API 호출 자체가 실패했을 때(e.g., 404) 호출됩니다."""
#         fallback_url = failure.request.meta['fallback_url']
#         self.logger.warning(f"[{self.company_name}] API 호출 실패. HTML 탐색 결과를 최종 URL로 확정합니다.")
#         self.found_url = fallback_url

#     def parse_api_response(self, response):
#         """API 응답을 분석하고, 성공 시 해당 URL로 다시 HTML 탐색을 시작합니다."""
#         meta = response.meta
#         try:
#             data = json.loads(response.text)
#             menu_list = data.get('menuList', [])
#             if not menu_list and 'result' in data and 'menuList' in data['result']:
#                 menu_list = data['result']['menuList']

#             for menu_item in menu_list:
#                 if menu_item.get('menuName') == self.TARGET_MENU_NAME:
#                     relative_url = menu_item.get('url')
#                     if relative_url:
#                         found_url = response.urljoin(relative_url)
#                         self.logger.info(f"✅ [{self.company_name}] API에서 URL 발견! 해당 URL로 탐색 재시작: {found_url}")
#                         # API로 찾은 URL에서 다시 HTML 탐색부터 시작
#                         yield scrapy.Request(
#                             found_url,
#                             callback=self.parse_navigation,
#                             meta={'depth': meta['depth'] + 1, 'previous_links': meta['previous_links']}
#                         )
#                         return # 성공했으므로 함수 종료
#         except Exception as e:
#             self.logger.error(f"[{self.company_name}] API 응답 처리 중 에러: {e}")

#         # API 호출은 성공했으나, 원하는 데이터가 없는 경우
#         fallback_url = meta['fallback_url']
#         self.logger.warning(f"[{self.company_name}] API에서 유효한 URL을 찾지 못함. HTML 탐색 결과를 최종 URL로 확정합니다.")
#         self.found_url = fallback_url
    
#     def save_url_to_db(self):
#         if not self.found_url:
#             self.logger.warning(f"⚠️ [{self.company_name}] 최종 URL을 확정하지 못했습니다.")
#             return

#         self.logger.info(f"✅ [{self.company_name}] 최종 채용 페이지 선정! URL: {self.found_url}")
#         if not self.cursor: return
#         try:
#             sql = "UPDATE companies SET recruits_url = %s, recruits_url_status = 'CONFIRMED' WHERE name = %s"
#             self.cursor.execute(sql, (self.found_url, self.company_name))
#             self.db_connection.commit()
#         except Exception as e:
#             self.logger.error(f"❌ [{self.company_name}] DB 저장 중 에러: {e}")

#     def closed(self, reason):
#         self.save_url_to_db()
#         if self.db_connection:
#             if self.cursor: self.cursor.close()
#             self.db_connection.close()
#             self.logger.info(f"[{self.company_name}] DB 연결 종료됨. 이유: {reason}")



import re
from urllib.parse import urljoin, urlparse

import scrapy
from scrapy import Request

from api.models import Company


PRIORITY_KEYWORDS = [
    "채용공고","채용 안내","채용안내","채용 정보","채용정보","채용",
    "인재채용","인재 모집","recruit","recruitment","career",
    "careers","jobs","employment","join us",
    '입사지원','채용사이트가기','채용중인공고','채용사이트',
    '채용절차','openpositions','집중채용', 
]

EXTERNAL_JOB_DOMAINS = [
    "saramin.co.kr",
    "jobkorea.co.kr",
    "wanted.co.kr",
]

MAX_DEPTH = 3  # 너무 깊이 안 들어가도록 제한


class DiscoverCareersSpider(scrapy.Spider):
    name = "discover_careers"

    custom_settings = {
        "LOG_LEVEL": "INFO",
        # 이 스파이더는 회사 1개 기준이므로 동시 요청 수 높일 필요 없음
        "CONCURRENT_REQUESTS": 4,
        "DOWNLOAD_DELAY": 0.3,
        "ROBOTSTXT_OBEY": False,
    }

    def __init__(self, company_id=None, company_name=None, homepage_url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not company_id or not homepage_url:
            raise ValueError("company_id와 homepage_url 인자가 필요합니다.")

        self.company_id = int(company_id)
        self.company_name = company_name or ""
        self.start_urls = [homepage_url]

        self.start_domain = urlparse(homepage_url).netloc
        self.visited = set()
        self.found = False

    # 공통 시작 포인트
    def start_requests(self):
        for url in self.start_urls:
            yield Request(url, callback=self.parse_page, meta={"depth": 0})

    # 메인 파서: 모든 페이지는 여기(or parse_candidate)를 거친다
    def parse_page(self, response):
        if self.found:
            return

        depth = response.meta.get("depth", 0)
        url = response.url

        self.logger.info("[discover] depth=%s url=%s", depth, url)

        # 1) 외부 구인 사이트 직접 연결?
        if self.is_external_jobboard(url):
            self.save_result(
                recruits_url=url,
                page_type="external",
                post_type="external_link",
            )
            return

        # 2) 현재 페이지가 채용 메인 페이지처럼 보이는지 판단
        if self.looks_like_listing(response):
            post_type = self.detect_post_type(response)
            self.save_result(
                recruits_url=url,
                page_type="listing",
                post_type=post_type,
            )
            return

        if self.looks_like_onepage(response):
            post_type = self.detect_post_type(response)
            # 시작 URL이면 메인에서 채용 안내하는 케이스로 간주 가능
            page_type = "main" if depth == 0 else "one_page"
            self.save_result(
                recruits_url=url,
                page_type=page_type,
                post_type=post_type,
            )
            return

        # 3) 아직 못 찾았고, 탐색 가능하면 다음 후보 링크들 선택
        if depth >= MAX_DEPTH:
            return

        for next_url in self.select_candidate_links(response):
            if self.found:
                break
            if next_url in self.visited:
                continue
            self.visited.add(next_url)
            yield Request(
                next_url,
                callback=self.parse_page,
                meta={"depth": depth + 1},
                dont_filter=True,
            )

    # -------------------------------
    # 선택 엔진: 우선순위 높은 링크 고르기
    # -------------------------------
    def select_candidate_links(self, response):
        candidates = []

        for a in response.css("a[href]"):
            href = (a.attrib.get("href") or "").strip()
            if not href or href.startswith("#") or href.lower().startswith("javascript:"):
                continue

            abs_url = urljoin(response.url, href)
            parsed = urlparse(abs_url)

            # 너무 엉뚱한 도메인으로 튀는 건 우선 제외 (외부 구인 사이트는 별도 처리)
            if (
                parsed.netloc
                and parsed.netloc != self.start_domain
                and not self.is_external_jobboard(abs_url)
            ):
                continue

            text_parts = [
                (a.attrib.get("title") or ""),
                (a.attrib.get("aria-label") or ""),
                "".join(a.css("::text").getall()),
            ]
            link_text = " ".join(t.strip() for t in text_parts if t).lower()

            score = 0

            # 키워드 매칭 점수
            for kw in PRIORITY_KEYWORDS:
                if kw.lower() in link_text:
                    score += 10
            # URL path 상의 키워드도 가산점
            path_lower = parsed.path.lower()
            for kw in ["career", "careers", "recruit", "recruitment", "join", "hire"]:
                if kw in path_lower:
                    score += 6

            # 외부 구인 서비스는 즉시 최우선
            if self.is_external_jobboard(abs_url):
                score += 100

            if score > 0:
                candidates.append((score, abs_url))

        # 점수 내림차순 정렬
        candidates.sort(key=lambda x: x[0], reverse=True)
        result = [url for score, url in candidates]

        if result:
            self.logger.info(
                "[discover] %s candidates from %s",
                len(result),
                response.url,
            )

        return result

    # -------------------------------
    # 판단 엔진: 이 페이지가 채용 페이지인가?
    # -------------------------------
    def looks_like_listing(self, response):
        """
        여러 개의 공고 링크/카드가 나열된 전형적인 '채용 리스트' 페이지인지.
        """
        body_text = " ".join(response.css("body *::text").getall()).lower()

        if "채용" not in body_text and "recruit" not in body_text and "career" not in body_text:
            return False

        # 공고 리스트로 보이는 링크/블록 개수
        job_like_links = 0
        for a in response.css("a[href]"):
            txt = "".join(a.css("::text").getall()).strip()
            if not txt:
                continue
            low = txt.lower()
            if any(
                kw in low
                for kw in ["채용", "모집", "공고", "지원", "입사지원", "apply", "position", "recruit"]
            ):
                job_like_links += 1

        # 대충 3개 이상 비슷한 링크 있으면 listing 가능성 높다고 본다
        return job_like_links >= 3

    def looks_like_onepage(self, response):
        """
        한 페이지 안에 회사 소개 + 복수의 포지션/조건이 텍스트로 잔뜩 있는 형식 등.
        """
        body_text = " ".join(response.css("body *::text").getall()).lower()

        if "채용" not in body_text and "recruit" not in body_text and "career" not in body_text:
            return False

        # 지원 관련 키워드 존재
        if any(
            kw in body_text
            for kw in ["지원방법", "전형절차", "제출서류", "채용절차", "근무조건", "모집분야", "접수방법"]
        ):
            return True

        return False

    def detect_post_type(self, response):
        """
        text vs image vs external_link 간 대략적 구분.
        - external_link: 외부 구인 사이트를 가리키는 경우
        - image: 텍스트는 거의 없고 이미지 위주인 경우 (대충 heuristic)
        - text: 기본값
        """
        url = response.url.lower()
        if self.is_external_jobboard(url):
            return "external_link"

        body_text = " ".join(response.css("body *::text").getall()).strip()
        img_count = len(response.css("img"))

        # 텍스트 거의 없고 이미지만 많은 경우 → image 기반 공고로 추정
        if img_count >= 3 and len(body_text) < 400:
            return "image"

        return "text"

    def is_external_jobboard(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return any(domain in host for domain in EXTERNAL_JOB_DOMAINS)

    # -------------------------------
    # 결과 저장
    # -------------------------------
    def save_result(self, recruits_url, page_type, post_type):
        if self.found:
            return
        self.found = True

        # region, hiring 은 여기서 과하게 추론하지 말고,
        # job_collector 단계에서/혹은 별도 로직에서 정교하게 처리하는 걸로 둔다.
        try:
            Company.objects.filter(id=self.company_id).update(
                recruits_url=recruits_url,
                recruits_url_status="CONFIRMED",
                page_type=page_type,
                post_type=post_type,
            )
            self.logger.info(
                "[discover] SAVED company_id=%s url=%s page_type=%s post_type=%s",
                self.company_id,
                recruits_url,
                page_type,
                post_type,
            )
        except Exception as e:
            self.logger.error(
                "[discover] FAILED TO SAVE company_id=%s url=%s: %s",
                self.company_id,
                recruits_url,
                e,
            )
