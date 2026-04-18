# 2026-04-10 Discovery Iteration Status

## Purpose

This document summarizes the current state of the recruit-page discovery work after:

- several smaller sample-based experiments,
- a 1,200-company baseline study,
- two iterative discovery-stage improvements,
- and the start of a 10,000-company final run using the currently selected logic.

The goal of this note is to preserve exactly what was tried, what was kept, what was reverted, and what is currently running.

---

## Product Principle Used During This Work

The project direction was clarified as follows:

- missing some real postings is acceptable,
- but recommending expired postings, non-job pages, or weakly parsed hiring 안내 pages is not acceptable,
- therefore precision and trust are more important than recall and total volume.

This principle was used to judge whether discovery-stage changes were worth keeping.

---

## Stable Changes Kept Before Discovery Iteration Work

These changes had already been implemented and were still kept during this phase:

1. **Range-aware crawl helpers**
   - `api/tasks.py`
   - `api/company_sources.py`

2. **Homepage liveness range checker**
   - `scripts/homepage_check_range.py`

3. **Internal auth header normalization**
   - `api/views_match.py`
   - `api/views_extract.py`

4. **Startup race fix**
   - `entrypoint.sh`
   - only the app/gunicorn path runs migration / schedule initialization

5. **Date validity filtering for job postings**
   - current valid rule:
     - keep when `deadline_at >= today`
     - or when `deadline_at is null` and `posted_at` is within the last 30 days

6. **Listing-date fallback in collector**
   - when detail page dates are missing, listing-page dates can be used as fallback
   - validated using a real case (`23048`, 시큐인)

7. **Stale posting expiration on successful company rerun**
   - postings not rediscovered during a fresh run are marked `expired / inactive`

---

## Discovery-Side Changes Attempted During This Phase

### A. Discovery response caching

Kept.

`crawler/crawler/spiders/discover_careers.py`

- response-level anchor/text reuse
- low-risk CPU reduction
- no observed regression in prior checks

### B. One-page deeper follow-up from generic pages

Reverted.

Why:

- sample-based comparison did not prove improvement
- one reviewed sample (`11309`) regressed and lost the previously stored recruit URL

Conclusion:

- not kept

### C. Aggressive high-confidence gate in collector

Reverted.

Why:

- filtered some weak postings successfully
- but also removed clearly useful postings in some companies (`10821`-class cases)
- precision gain was not clean enough to justify the false-negative risk

Conclusion:

- not kept

### D. Lightweight post-discovery verifier

Reverted.

Why:

- tested on representative and targeted samples
- did not produce measurable improvements in the reviewed cases

Conclusion:

- not kept

### E. Hard stop after first confident discovery save

Kept.

`crawler/crawler/spiders/discover_careers.py`

- `self.found` latch added
- once a confident result is saved, later callbacks no longer overwrite it

Why it was kept:

- no observed regression in sample comparisons
- reduces overwrite risk and unnecessary later saves
- low-risk structural improvement

### F. Direct recruit-link ranking instead of first-match selection

Kept.

`crawler/crawler/spiders/discover_careers.py`

Instead of returning the first same-domain recruit-like link in DOM order, the logic now:

- scores same-domain candidates using anchor text/label score,
- adds bonus for stronger URL path tokens such as:
  - `recruit`
  - `career`
  - `jobs`
  - `job_notice`
  - `employment`
- subtracts score for weaker path tokens such as:
  - `culture`
  - `story`
  - `people`
  - `benefit`
  - `about`

This was the second tested improvement and is the current selected discovery refinement.

---

## 1,200-Company Discovery Evaluation

### Cohort

- Company ID range: `1 ~ 1200`

Initial cohort stats before rerun:

- total: `1200`
- with homepage: `1185`
- homepage alive: `960`
- already having `recruits_url`: `298`

### Baseline discovery-only run

Run result:

- target companies: `1052`
- saved: `1052`
- failed: `0`
- elapsed: about `1879.71s` (~31m 20s)

Baseline resulting counts on the cohort:

- with `recruits_url`: `337`
- `listing`: `123`
- `one_page`: `99`
- `main`: `86`
- `external`: `29`

### Iteration 1 (light verifier + hard stop path during testing)

Observed summary:

- with `recruits_url`: `242`
- `listing`: `123`
- `one_page`: `82`
- `main`: `15`
- `external`: `22`

This changed too many outcomes and produced mixed quality results.

Representative manual outcomes:

- improved:
  - `104` 두나무 (`story` → `jobs`)
  - `452` 동아대학교 산학협력단 (non-job page → actual hiring notice)
  - `592` 옥타솔루션 (single article → listing page)
- regressed:
  - `58` 에스넷시스템 (`job_application` → `culture` in one earlier trial)
  - several cases became too broad or too weak

Conclusion:

- not kept in that form

### Iteration 2 (direct-link ranking + hard stop)

Final observed summary:

- with `recruits_url`: `335`
- `listing`: `123`
- `one_page`: `97`
- `main`: `85`
- `external`: `30`

This is much closer to the baseline than iteration 1, while still improving some clear cases.

Representative manual outcomes:

- improved:
  - `58` 에스넷시스템: `404` old path → `https://www.snetsystems.co.kr/careers`
  - `104` 두나무: `story`-leaning page → `https://www.dunamu.com/careers/jobs`
  - `452` 동아대학교 산학협력단: general movement/news page → actual hiring notice post
  - `592` 옥타솔루션: single hiring article → listing page with multiple hiring/news rows
- still weak / ambiguous:
  - `205` 롯데: still lands on general careers info page
  - `296` 코멘토: career-like page but still broad and mixed
  - `320` 아이쉴드: still not a real hiring page

Judgment:

- improvement is real in several representative URL-choice cases
- no mass collapse in discovered counts
- better than iteration 1
- kept as the currently selected discovery refinement

---

## Manual Review Scale Achieved So Far

Discovery pages were manually reviewed in several waves.

- earlier 20-company reviewed sample
- expanded 32-company reviewed sample
- 120-page sampled snapshot was also generated from the `1~1200` cohort for broader review work

The 120-page fetch file was created at:

- `/app/data/2026-04-09_manual_review_sample_120_fetched.tsv`

This file contains:

- company id
- company name
- page type
- post type
- recruit URL
- HTTP status
- page title
- page text preview
- request error (if any)

---

## Current Discovery Logic Summary

The current selected discovery logic now has these important properties:

1. **direct recruit link path still has highest priority**
2. **same-domain candidate links are scored rather than taking the first DOM match**
3. **response-level caching reduces repeated parsing work**
4. **first successful save becomes sticky via hard stop**
5. broad post-discovery verifier experiments were removed because they were not proven useful
6. broad one-page tightening experiments were removed because they were not proven useful

In plain terms:

- the spider still uses the same overall structure,
- but it now makes a better first-link choice and is less likely to overwrite a good discovered result later.

---

## Final 10,000-Company Run Result

The final selected logic was applied to:

- Company ID range: `1 ~ 10000`

Execution mode:

- `rerun_company_crawl_range`
- `chunk_size=50`
- `workers=2`

This run performed both:

- recruit-page rediscovery
- downstream job collection

Final observed counts on the `1 ~ 10000` range:

- companies: `10000`
- with `recruits_url`: `2182`
- `listing`: `858`
- `one_page`: `643`
- `main`: `447`
- `external`: `234`
- active `JobPosting`: `68`

This aligns with the reliability-first product principle used during this work:

- the system now captures a much larger recruit-page set,
- but only a relatively small, current active job-posting set remains in the downstream DB,
- which is acceptable because the goal is trustworthy current postings rather than maximum volume.

---

## Practical Interpretation of the Results So Far

The current state supports these conclusions:

1. **Discovery is not fundamentally broken.**
   - baseline and iterative runs complete with `failed=0` on the tested cohort.

2. **Broad one-page / main false positives still exist.**
   - some careers/people/culture/info pages are still accepted.

3. **Large aggressive precision gates were not safe enough.**
   - they either did not improve enough or removed too much.

4. **Small structural improvements were safer and more defensible.**
   - hard stop
   - better direct-link ranking

5. **For recommendation trust, later-stage filtering is still important.**
   - discovery alone cannot guarantee recommendation-grade precision.

---

## Files Most Relevant to This Phase

- `crawler/crawler/spiders/discover_careers.py`
- `crawler/crawler/spiders/job_collector.py`
- `api/llm_parser.py`
- `api/tasks.py`
- `docs/2026-04-09_listing_date_fallback_validation.md`
- `docs/2026-04-02_final_batch_and_export_report.md`

---

## Final Status at This Checkpoint

- Discovery experiments were run conservatively on larger cohorts, not only tiny handpicked samples.
- Only evidence-backed discovery changes are currently kept.
- The selected logic has already been applied to a 10,000-company run.
- Final DB snapshots were exported as dated CSV files:
  - `data/2026-04-10_companies_snapshot.csv`
  - `data/2026-04-10_job_postings_snapshot.csv`

### Final kept discovery-side changes

1. **response caching** in `discover_careers.py`
2. **hard stop after first confident save** in `discover_careers.py`
3. **better direct recruit-link ranking** in `find_direct_recruit_link()`

### Final non-kept discovery-side experiments

1. deeper follow from generic one-page pages
2. stricter one-page acceptance tweak
3. lightweight post-discovery verifier

These were tested and deliberately reverted when the evidence was weak or regressions were observed.
