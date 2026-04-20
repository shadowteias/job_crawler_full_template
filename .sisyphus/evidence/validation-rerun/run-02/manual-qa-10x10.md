# Manual QA (10 Recruit Pages + 10 Job Records)

- Validation run: `run-02` (success iteration = 2)
- Sampling seed: `20260420`
- Inspection method: URL fetch + content/routing sanity check

## Recruit Page QA (10)

| # | Company | URL | Verdict | Notes |
|---|---|---|---|---|
| 1 | 주식회사 슬링 | https://sling.ninehire.site | PASS | Dedicated hiring homepage with company intro and recruit sections. |
| 2 | (주)하이텍정보시스템 | http://hitecis.co.kr/recruit.html | PASS | Recruit section includes hiring roles and application guidance. |
| 3 | (주)에스제이더블유인터내셔널 | https://recruit.siwonschool.com | PASS | Official recruit portal; zero open postings is still valid. |
| 4 | (주)허브넷컴퍼니 | http://www.hubnet.kr/board/bbs/board.php?bo_table=incruit | PASS | Company recruit board endpoint; currently no posts. |
| 5 | (주)에이펀인터렉티브 | http://www.afun-interactive.com/career/sub01.html?PHPSESSID=cc6b866876726811efce09ffed0f6446 | PASS | Career page with role categories and recruit messaging. |
| 6 | 주식회사 라피치 | https://www.rapeech.com/notice/recruit | PASS | Recruit process and eligibility details present. |
| 7 | 주식회사 어바웃그룹 | http://www.aboutgroup.co.kr/page.php?p_id=joinus | PASS | Join-us page with explicit hiring process and contact. |
| 8 | (주)잡앤피플연구소 | https://jobnlab.co.kr/front/sub_process.asp | FAIL | HR outsourcing process page, not the company’s own hiring board. |
| 9 | 주식회사 이스파이스 | http://espice.co.kr/?page_id=1348 | PASS | Recruit page includes application instructions and submission email. |
| 10 | 주식회사 오토노머스에이투지 | https://autoa2z.co.kr/culture | FAIL | Culture page, not direct recruit posting/listing endpoint. |

Recruit-page precision in sample: **8/10 (80%)**.

## Job Posting QA (10)

| # | DB Job ID | URL | Verdict | Notes |
|---|---:|---|---|---|
| 1 | 540 | https://www.finetechnix.com/company/talent#job-d9e5c3d5-10 | FAIL | Generic talent page, not a specific posting detail. |
| 2 | 539 | https://www.kipa.org/kipa/notice/recruit_notice.jsp?mode=view&article_no=122389&board_wrapper=%2Fkipa%2Fnotice%2Frecruit_notice.jsp&pager.offset=0&board_no=1345 | PASS (partial) | Real posting detail exists; DB title `알림광장` is too generic. |
| 3 | 528 | https://www.kipa.org/kipa/notice/recruit_notice.jsp?mode=list&board_no=1345&pager.offset=70 | FAIL | Listing page only, not a posting detail URL. |
| 4 | 509 | http://www.afun-interactive.com/career/sub01.html?PHPSESSID=cc6b866876726811efce09ffed0f6446#job-33f74a5a-0 | FAIL | Career overview page; no clear per-job detail at anchor level. |
| 5 | 510 | https://webonomics.co.kr/new/html/recruit.php | FAIL | Generic recruit application page, not a concrete job posting. |
| 6 | 531 | https://www.kipa.org/kipa/notice/recruit_notice.jsp?mode=view&article_no=113391&board_wrapper=%2Fkipa%2Fnotice%2Frecruit_notice.jsp&pager.offset=0&board_no=1345 | PASS (partial) | Posting detail exists; DB title normalization is weak. |
| 7 | 511 | https://www.tsline.co.kr/career#job-0773abd2-0 | FAIL | Career process page, not a specific job posting detail. |
| 8 | 525 | http://recruit.krindus.co.kr | FAIL | Recruit main page; currently no active posting detail shown. |
| 9 | 524 | http://www.smtkorea.co.kr/bbs/board.php?bo_table=board3 | FAIL | Broad board listing with mixed posts, not a unique job detail record. |
| 10 | 536 | https://www.kipa.org/kipa/notice/recruit_notice.jsp?mode=view&article_no=122373&board_wrapper=%2Fkipa%2Fnotice%2Frecruit_notice.jsp&pager.offset=0&board_no=1345 | PASS (partial) | Posting detail exists; stored title still generic. |

Job-record precision in sample: **3/10 strict PASS**, **3/10 partial PASS**, **4/10 FAIL**.

## QA Conclusion

- Discovery threshold was achieved (recruit pages and postings counts), but URL-level precision remains mixed.
- Main error pattern: job records saved with listing/career overview URLs instead of detail-level posting URLs.
- Immediate hardening priority:
  1. Reject broad listing endpoints (`mode=list`, board root, generic `/career` pages) as final `post_url`.
  2. Strengthen detail-page detection before `upsert_jobposting`.
  3. Normalize title extraction to avoid placeholder labels like `알림광장`.
