#!/usr/bin/env python3
"""Quick test script to find recruit URLs for specific companies"""
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import warnings
warnings.filterwarnings('ignore')

PRIORITY_KEYWORDS = ['채용', '채용공고', '채용안내', '인재', 'recruit', 'recruitment', 'career', 'careers', 'jobs', 'employment', 'job', 'join us']
MENU_INDICATORS = ['인재', '채용', 'recruit', 'career', ' job', 'employment', '입사', '공고', '모집', 'hiring']
EXTERNAL_JOB_DOMAINS = ['wanted.co.kr', 'saramin.co.kr', 'jobkorea.co.kr', 'incruit.co.kr', 'worknet.or.kr']

def get_page(url, timeout=8):
    try:
        r = requests.get(url, timeout=timeout, verify=False, allow_redirects=True)
        return r.text, r.url
    except:
        return None, None

def find_recruit_links(html, base_url):
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
        if href.startswith('javascript:'):
            continue
        full_url = urljoin(base_url, href)
        if any(d in full_url.lower() for d in EXTERNAL_JOB_DOMAINS):
            continue
        combined = (text + ' ' + title).lower()
        if any(kw.lower() in combined for kw in PRIORITY_KEYWORDS):
            if full_url not in [l[1] for l in links]:
                links.append((text, full_url))
    return links

def get_menu_links(html, base_url):
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
        is_job_related = any(ind in text.lower() for ind in MENU_INDICATORS)
        max_len = 30 if is_job_related else 20
        if len(text) > max_len and not is_job_related:
            continue
        full_url = urljoin(base_url, href)
        if urlparse(full_url).netloc != base_domain:
            continue
        if full_url.rstrip('/') == base_url.rstrip('/'):
            continue
        links.append((text, full_url, is_job_related))
    links.sort(key=lambda x: (not x[2], len(x[0])))
    return links

def discover_careers_page(url, max_depth=2):
    html, final_url = get_page(url)
    if not html:
        return None, 'error'
    
    direct_links = find_recruit_links(html, final_url)
    if direct_links:
        return direct_links[0][1], 'direct'
    
    menu_links = get_menu_links(html, final_url)
    visited = {final_url}
    
    for menu_text, menu_url, is_job in menu_links[:15]:
        if menu_url in visited:
            continue
        visited.add(menu_url)
        
        html1, _ = get_page(menu_url)
        if not html1:
            continue
        
        links1 = find_recruit_links(html1, menu_url)
        if links1:
            return links1[0][1], f'depth1-{menu_text}'
        
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
                return links2[0][1], f'depth2-{menu_text}>{sub_text}'
    
    return None, 'not_found'

# Companies to test
companies = [
    (32511, "포인트엔지니어링", "https://www.pointeng.co.kr"),
    (32512, "대유", "https://www.dae-yu.co.kr"),
    (32513, "제이피아이헬스케어", "https://www.jpi-korea.com"),
    (32517, "와이엠티", "https://www.ymtechnology.com"),
    (32518, "그린광학", "https://www.greenoptics.com/"),
    (32519, "더즌", "https://www.dozn.co.kr/"),
    (32522, "삼양사", "https://www.samyangcorp.com"),
    (32523, "삼양바이오팜", "https://www.samyangbiopharm.com"),
    (32525, "노보믹스", "https://novomics.com/"),
    (32526, "동방아그로", "https://www.dongbangagro.co.kr"),
]

print(f"=== Testing {len(companies)} companies ===\n")

results = []
for company_id, name, url in companies:
    print(f"Testing: {name} ({url})")
    try:
        result, status = discover_careers_page(url)
        if result:
            print(f"  ✅ Found: {result[:60]}... [{status}]")
            results.append((company_id, name, url, result, status))
        else:
            print(f"  ❌ Not found ({status})")
    except Exception as e:
        print(f"  ❌ Error: {str(e)[:50]}")

print(f"\n=== Results: {len(results)}/{len(companies)} found ===")

# SQL to update companies
print("\n=== SQL to update companies ===")
for company_id, name, homepage, recruit_url, status in results:
    print(f"UPDATE companies SET recruits_url = '{recruit_url}', recruits_url_status = 'CONFIRMED', page_type = 'listing', post_type = 'text' WHERE id = {company_id};")
