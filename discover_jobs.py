"""
채용 페이지 탐색 - 메뉴 기반 우선 탐색 로직
"""

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import warnings
warnings.filterwarnings('ignore')

# 채용 관련 키워드
PRIORITY_KEYWORDS = [
    '채용', '채용공고', '채용안내', '채용 정보', '인재', 'recruit', 'recruitment',
    'career', 'careers', 'jobs', 'employment', 'job', 'join us', '입사', '채용사이트'
]

# 채용 관련 메뉴 indicators (우선 탐색)
MENU_INDICATORS = [
    '인재', '채용', 'recruit', 'career', ' job', 'employment', '입사', '공고', '모집', 'hiring'
]

# 외부 채용 플랫폼 (크롤링 금지)
EXTERNAL_JOB_DOMAINS = ['wanted.co.kr', 'saramin.co.kr', 'jobkorea.co.kr', 'incruit.co.kr', 'worknet.or.kr']

# 채용 페이지 검증 키워드
JOB_VALIDATION_KEYWORDS = [
    '채용', '공고', '모집', '자격', '우대', '근무', '직무', '연봉', '지원', '복리후생',
    '신입', '경력', '채용공고', '채용요강', '채용기간', '마감',
    'recruit', 'job', 'position', 'application', 'apply', 'hiring',
    'qualification', 'requirement', 'benefit', 'salary'
]

# 부정 키워드 (채용 절차, FAQ 등 - 제외)
NOT_JOB_KEYWORDS = [
    '채용절차', '모집절차', '지원방법', 'FAQ', '자주하는질문', 'QnA', '지원서양식'
]


def get_page(url, timeout=8):
    """HTML 페이지 가져오기"""
    try:
        r = requests.get(url, timeout=timeout, verify=False, allow_redirects=True)
        return r.text, r.url
    except:
        return None, None


def is_external_job_link(url):
    """외부 채용 플랫폼 링크인지 확인"""
    return any(d in url.lower() for d in EXTERNAL_JOB_DOMAINS)


def find_recruit_links(html, base_url):
    """채용 관련 키워드가 있는 링크 찾기"""
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    links = []
    
    for a in soup.find_all('a', href=True):
        href = a.get('href', '').strip()
        text = a.get_text(strip=True)
        title = a.get('title', '') or ''
        
        if not href or not text:
            continue
        
        # JavaScript 링크 제외
        if href.startswith('javascript:'):
            continue
        
        full_url = urljoin(base_url, href)
        
        # 외부 채용 플랫폼 제외
        if is_external_job_link(full_url):
            continue
        
        # 키워드 체크
        combined = (text + ' ' + title).lower()
        if any(kw.lower() in combined for kw in PRIORITY_KEYWORDS):
            if full_url not in [l[1] for l in links]:
                links.append((text, full_url))
    
    return links


def get_menu_links(html, base_url, exclude_texts=None):
    """메뉴-like 링크 수집 - 채용 관련 우선"""
    if exclude_texts is None:
        exclude_texts = set()
    
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    links = []
    base_domain = urlparse(base_url).netloc
    
    for a in soup.find_all('a', href=True):
        href = a.get('href', '').strip()
        text = a.get_text(strip=True)
        
        if not href or not text:
            continue
        
        # 제외할 텍스트
        if text in exclude_texts:
            continue
        
        # 채용 관련 텍스트 여부
        is_job_related = any(ind in text.lower() for ind in MENU_INDICATORS)
        
        # 일반 메뉴: 25자 이하, 채용 관련: 30자 이하
        max_len = 30 if is_job_related else 20
        if len(text) > max_len and not is_job_related:
            continue
        
        full_url = urljoin(base_url, href)
        
        # 동일 도메인만
        if urlparse(full_url).netloc != base_domain:
            continue
        
        # 동일 페이지 제외
        if full_url.rstrip('/') == base_url.rstrip('/'):
            continue
        
        links.append((text, full_url, is_job_related))
    
    # 채용 관련 메뉴를 먼저 반환 (우선순위)
    links.sort(key=lambda x: (not x[2], len(x[0])))
    return links


def validate_job_page(url):
    """채용 페이지 검증"""
    try:
        r = requests.get(url, timeout=8, verify=False)
        soup = BeautifulSoup(r.text, 'html.parser')
        text = soup.get_text().lower()
        
        # 부정 키워드 먼저 체크
        not_job_count = sum(1 for kw in NOT_JOB_KEYWORDS if kw.lower() in text)
        if not_job_count >= 2:
            return False
        
        # 긍정 키워드 체크
        job_count = sum(1 for kw in JOB_VALIDATION_KEYWORDS if kw.lower() in text)
        
        # 제목에서 채용 키워드 확인
        title = soup.find('title')
        title_text = title.get_text().lower() if title else ''
        title_job = any(kw in title_text for kw in ['채용', ' recruit', ' job', ' careers', ' employment'])
        
        return job_count >= 3 or (job_count >= 1 and title_job)
    
    except:
        return False


def discover_careers_page(url, max_depth=2):
    """
    메뉴 기반 채용 페이지 탐색 (depth 2)
    1. 채용 키워드 링크 직접 탐색
    2. 메뉴 기반 순차 탐색
    """
    
    # depth 0: 메인 페이지
    html, final_url = get_page(url)
    if not html:
        return None, None, 'error'
    
    # 직접 채용 링크 찾기 (우선)
    direct_links = find_recruit_links(html, final_url)
    if direct_links:
        is_valid = validate_job_page(direct_links[0][1])
        return direct_links[0][1], is_valid, 'direct'
    
    # 메뉴 기반 탐색
    menu_links = get_menu_links(html, final_url)
    
    visited = {final_url}
    
    # depth 1: 메뉴 탐색
    for menu_text, menu_url, is_job in menu_links[:15]:
        if menu_url in visited:
            continue
        visited.add(menu_url)
        
        html1, _ = get_page(menu_url)
        if not html1:
            continue
        
        # 채용 링크 확인
        links1 = find_recruit_links(html1, menu_url)
        if links1:
            is_valid = validate_job_page(links1[0][1])
            return links1[0][1], is_valid, f'depth1-{menu_text}'
        
        # depth 2: 서브 메뉴
        sub_menu = get_menu_links(html1, menu_url)
        for sub_text, sub_url, _ in sub_menu[:10]:
            if sub_url in visited:
                continue
            visited.add(sub_url)
            
            html2, _ = get_page(sub_url)
            if not html2:
                continue
            
            links2 = find_recruit_links(html2, sub_url)
            if links2:
                is_valid = validate_job_page(links2[0][1])
                return links2[0][1], is_valid, f'depth2-{menu_text}>{sub_text}'
    
    return None, None, 'not_found'


if __name__ == '__main__':
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    
    import django
    django.setup()
    
    from api.models import Company
    
    # 35개 회사 테스트
    companies = Company.objects.filter(
        homepage_url_status='alive'
    ).exclude(
        recruits_url__isnull=False
    ).exclude(
        recruits_url=''
    ).order_by('?')[:35]
    
    print(f'=== 메뉴 기반 탐색 테스트 ({companies.count()}개) ===\n')
    
    results = []
    
    for c in companies:
        url = c.homepage_url
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        
        try:
            result, is_valid, status = discover_careers_page(url)
            if result:
                results.append((c.name, result, status, is_valid))
        except Exception as e:
            pass
    
    # 결과 분석
    found = len(results)
    valid = sum(1 for r in results if r[3])
    
    print(f'발견: {found}/{companies.count()} ({(found*100)//companies.count()}%)')
    print(f'유효: {valid}/{found} ({(valid*100)//max(found,1)}%)')
    print(f'\\n=== 유효한 채용 페이지 ===')
    
    for name, url, status, is_valid in results:
        if is_valid:
            print(f'✅ {name}')
            print(f'   {url}')
            print(f'   [{status}]')
            print()
