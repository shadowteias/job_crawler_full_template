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





# 파일명: crawler/spiders/discover_careers.py
# 이 코드로 기존 파일의 내용을 완전히 덮어쓰세요.

import scrapy
from urllib.parse import urlparse, urljoin
import mariadb
from dotenv import load_dotenv
import os
import json
import re

load_dotenv()

class DiscoverCareersSpider(scrapy.Spider):
    name = 'discover_careers'

    # --- 설정 값 ---
    TARGET_API_KEYWORD = "getMainView"
    TARGET_MENU_NAME = "채용공고"
    PRIORITY_KEYWORDS = [
        '채용공고', '채용', '채용안내', '채용정보', 
        '채용사이트가기', '채용사이트', 'career', 'recruit', 'employment'
    ]
    MAX_DEPTH = 5

    def __init__(self, company_name=None, homepage_url=None, *args, **kwargs):
        super(DiscoverCareersSpider, self).__init__(*args, **kwargs)
        if not company_name or not homepage_url:
            raise ValueError("company_name과 homepage_url 인자가 필요합니다.")
            
        self.company_name = company_name
        self.homepage_url = homepage_url
        self.found_url = None
        self.visited_urls = set()

        # DB 연결
        self.db_connection = None
        self.cursor = None
        try:
            self.db_connection = mariadb.connect(
                host=os.getenv('DB_HOST'), user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'), database=os.getenv('DB_NAME'),
                port=int(os.getenv('DB_PORT'))
            )
            self.cursor = self.db_connection.cursor()
        except mariadb.Error as err:
            self.logger.error(f"❌ [{self.company_name}] DB 연결 오류: {err}")

    def start_requests(self):
        """항상 HTML 우선 탐색(전략 2)부터 시작합니다."""
        self.logger.info(f"[{self.company_name}] HTML 우선 탐색을 시작합니다: {self.homepage_url}")
        yield scrapy.Request(
            self.homepage_url, 
            callback=self.parse_navigation, 
            meta={'depth': 1, 'previous_links': set()}
        )

    def normalize_text(self, text):
        return re.sub(r'\s+', '', text).lower().strip()

    def parse_navigation(self, response):
        """[핵심] 1. HTML 링크를 먼저 찾고, 없으면 2. API를 시도합니다."""
        if self.found_url: return
        current_url = response.url
        if current_url in self.visited_urls: return
        self.visited_urls.add(current_url)
        current_depth = response.meta['depth']
        previous_links = response.meta.get('previous_links', set())
        self.logger.info(f"[{self.company_name}][깊이:{current_depth}] HTML 탐색 중: {current_url}")

        # 1. HTML 우선 탐색
        found_links_on_this_page = []
        for link in response.css('a'):
            href = link.css('::attr(href)').get()
            normalized_text = self.normalize_text("".join(link.css('::text').getall()))
            if not href or not normalized_text or href.startswith(('#', 'javascript:')): continue
            if normalized_text in self.PRIORITY_KEYWORDS:
                priority = self.PRIORITY_KEYWORDS.index(normalized_text)
                full_url = response.urljoin(href)
                found_links_on_this_page.append((priority, full_url))
        
        next_candidate_links = [link for link in found_links_on_this_page if link[1] not in previous_links]
        
        if next_candidate_links and current_depth < self.MAX_DEPTH:
            next_candidate_links.sort()
            highest_priority_url = next_candidate_links[0][1]
            if highest_priority_url not in self.visited_urls:
                current_page_urls_set = {url for _, url in found_links_on_this_page}
                yield scrapy.Request(
                    highest_priority_url, 
                    callback=self.parse_navigation, 
                    meta={'depth': current_depth + 1, 'previous_links': current_page_urls_set}
                )
                return

        # 2. HTML 링크가 없다면, 현재 페이지에서 API 탐색 시도
        self.logger.warning(f"[{self.company_name}] HTML 탐색 후보 없음. 현재 페이지에서 API 탐색 시도...")
        parsed_uri = urlparse(current_url)
        base_url = f"{parsed_uri.scheme}://{parsed_uri.netloc}"
        api_url = urljoin(base_url, f"/appsite/company/{self.TARGET_API_KEYWORD}")
        
        yield scrapy.Request(
            api_url,
            callback=self.parse_api_response,
            errback=self.handle_api_failure,
            meta={
                'depth': current_depth,
                'previous_links': {url for _, url in found_links_on_this_page},
                'fallback_url': current_url # API 실패 시 돌아올 URL
            }
        )
    
    def handle_api_failure(self, failure):
        """API 호출 자체가 실패했을 때(e.g., 404) 호출됩니다."""
        fallback_url = failure.request.meta['fallback_url']
        self.logger.warning(f"[{self.company_name}] API 호출 실패. HTML 탐색 결과를 최종 URL로 확정합니다.")
        self.found_url = fallback_url

    def parse_api_response(self, response):
        """API 응답을 분석하고, 성공 시 해당 URL로 다시 HTML 탐색을 시작합니다."""
        meta = response.meta
        try:
            data = json.loads(response.text)
            menu_list = data.get('menuList', [])
            if not menu_list and 'result' in data and 'menuList' in data['result']:
                menu_list = data['result']['menuList']

            for menu_item in menu_list:
                if menu_item.get('menuName') == self.TARGET_MENU_NAME:
                    relative_url = menu_item.get('url')
                    if relative_url:
                        found_url = response.urljoin(relative_url)
                        self.logger.info(f"✅ [{self.company_name}] API에서 URL 발견! 해당 URL로 탐색 재시작: {found_url}")
                        # API로 찾은 URL에서 다시 HTML 탐색부터 시작
                        yield scrapy.Request(
                            found_url,
                            callback=self.parse_navigation,
                            meta={'depth': meta['depth'] + 1, 'previous_links': meta['previous_links']}
                        )
                        return # 성공했으므로 함수 종료
        except Exception as e:
            self.logger.error(f"[{self.company_name}] API 응답 처리 중 에러: {e}")

        # API 호출은 성공했으나, 원하는 데이터가 없는 경우
        fallback_url = meta['fallback_url']
        self.logger.warning(f"[{self.company_name}] API에서 유효한 URL을 찾지 못함. HTML 탐색 결과를 최종 URL로 확정합니다.")
        self.found_url = fallback_url
    
    def save_url_to_db(self):
        if not self.found_url:
            self.logger.warning(f"⚠️ [{self.company_name}] 최종 URL을 확정하지 못했습니다.")
            return

        self.logger.info(f"✅ [{self.company_name}] 최종 채용 페이지 선정! URL: {self.found_url}")
        if not self.cursor: return
        try:
            sql = "UPDATE companies SET recruits_url = %s, recruits_url_status = 'CONFIRMED' WHERE name = %s"
            self.cursor.execute(sql, (self.found_url, self.company_name))
            self.db_connection.commit()
        except Exception as e:
            self.logger.error(f"❌ [{self.company_name}] DB 저장 중 에러: {e}")

    def closed(self, reason):
        self.save_url_to_db()
        if self.db_connection:
            if self.cursor: self.cursor.close()
            self.db_connection.close()
            self.logger.info(f"[{self.company_name}] DB 연결 종료됨. 이유: {reason}")




