# Validation Rerun and Push

## TL;DR
> **Summary**: Validate the current integration branch by running Docker startup checks, executing isolated rerun batches over randomly sampled alive-homepage companies, repeating until recollection thresholds are met, then producing a docs report and waiting for user approval before push.
> **Deliverables**:
> - isolated validation run over random 50-company batches
> - reproducible sampling/counter/evidence artifacts
> - `docs/` markdown validation report
> - approval-gated git push
> **Effort**: Large
> **Parallel**: YES - 3 waves
> **Critical Path**: 1 → 2 → 3/4 → 5 → 6 → 7 → 8

## Context
### Original Request
Run Docker validation, repeatedly sample 50 companies, clear prior recruit-page and job-posting results for each sampled company, rerun discovery and job collection until recollected recruit-page count exceeds 20 and recollected job-posting count exceeds 30, manually validate 10 recruit pages and 10 job postings, save the analysis as markdown under `docs/`, then push after user approval.

### Interview Summary
- Sampling pool: only companies with alive homepage URLs.
- Existing job postings: delete per sampled company before recollecting.
- Final report: write under `docs/`, then ask the user for approval before push.

### Metis Review (gaps addressed)
- Treat the run as destructive validation and require a dedicated validation DB before any delete.
- Disable beat/overlapping workers so counts are attributable to this run only.
- Freeze sample IDs and per-iteration counters as evidence.
- Define “newly collected” as rows/fields recreated during the current validation run after reset/delete, not historical novelty.
- Bound the loop to avoid infinite retry behavior.

## Work Objectives
### Core Objective
Produce a reproducible validation run that proves the current branch can restart from Docker, rerun discovery/collection for sampled alive-homepage companies, reach minimum recollection thresholds, and withstand manual quality inspection before any push.

### Deliverables
- Validation environment safety check evidence
- Random-sample batch execution artifacts for each iteration
- Threshold summary showing `recruits_url` recollection count > 20 and recollected `JobPosting` count > 30
- Manual QA evidence for 10 recruit pages and 10 job postings
- `docs/validation/2026-04-20-random-rerun-validation.md`
- Approval-gated push record

### Definition of Done (verifiable conditions with commands)
- Docker services required for validation are up and healthy.
- Every validation iteration records the sampled company IDs, pre-reset counts, post-reset counts, post-rerun counts, and thresholds.
- At least one iteration set reaches both thresholds: recollected recruit-page count > 20 and recollected job-posting count > 30.
- 10 recruit pages and 10 job postings are manually reviewed with saved evidence.
- Final validation report exists under `docs/validation/` and cites the evidence paths.
- No push occurs before explicit user approval.

### Must Have
- Dedicated validation DB/environment confirmation before deletes
- Sampling without replacement across the session until pool exhaustion
- Beat disabled and no overlapping crawl workers during validation
- Per-company deletion of existing `JobPosting` rows for sampled companies
- Reproducible sample/evidence artifacts stored during the run

### Must NOT Have
- No execution against shared or production-like DB volumes
- No global wipes (`docker compose down -v`, whole-table deletes outside sampled companies)
- No undocumented threshold counting from global table totals
- No push before user says okay
- No committing `.env`, logs, raw exported data, or other noisy/generated artifacts unless explicitly requested

## Verification Strategy
> ZERO HUMAN INTERVENTION - all verification is agent-executed.
- Test decision: tests-after using Docker + Django shell/management commands + browser evidence capture
- QA policy: Every task includes agent-executed scenarios and saved evidence
- Evidence root: `.sisyphus/evidence/validation-rerun/`
- Final report target: `docs/validation/2026-04-20-random-rerun-validation.md`

## Execution Strategy
### Parallel Execution Waves
Wave 1: safety/isolation/frozen-sample foundations
Wave 2: iteration loop execution and threshold attribution
Wave 3: manual QA, reporting, approval gate, push

### Dependency Matrix (full, all tasks)
- 1 blocks 2-8
- 2 blocks 3-8
- 3 blocks 4-8
- 4 blocks 5-8
- 5 blocks 6-8
- 6 blocks 7-8
- 7 blocks 8
- 8 blocks final verification

### Agent Dispatch Summary
- Wave 1 → 3 tasks → unspecified-high, quick
- Wave 2 → 3 tasks → unspecified-high, deep
- Wave 3 → 2 tasks → writing, unspecified-high

## TODOs
> Implementation + Test = ONE task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

- [ ] 1. Lock validation environment and capture safety baseline

  **What to do**: Confirm the run is targeting a dedicated validation DB and isolated docker stack. Record compose project name, DB host/port/name, mounted volumes, active services, and whether beat/other workers are disabled. Refuse to continue if the DB cannot be distinguished from shared/prod-like state. Create `.sisyphus/evidence/validation-rerun/env-baseline.md` with the exact environment proof.
  **Must NOT do**: Do not delete data, start crawls, or run validation against an ambiguous/shared database.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: environment safety and destructive-operation guardrails
  - Skills: `[]` - no extra skill required
  - Omitted: `['git-master']` - git is not the primary concern yet

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 2,3,4,5,6,7,8 | Blocked By: none

  **References**:
  - Pattern: `docker-compose.yml` - compose services, DB volume, external network
  - Pattern: `README.md` - startup commands and service expectations
  - Pattern: `config/settings.py` - DB/log configuration
  - Pattern: `.sisyphus/drafts/project-handoff-summary.md` - operational commands already used by the project

  **Acceptance Criteria**:
  - [ ] `docker compose ps` output is saved and shows required services running for validation.
  - [ ] Evidence file identifies DB target and explicitly states why it is safe for destructive validation.
  - [ ] Beat/overlapping workers are confirmed stopped or excluded before proceeding.

  **QA Scenarios**:
  ```
  Scenario: Validation DB proven safe
    Tool: Bash
    Steps: Start required services; capture `docker compose ps`; inspect app/worker config and DB env values; write baseline evidence.
    Expected: Evidence explicitly names the validation DB target and confirms no shared/prod ambiguity.
    Evidence: .sisyphus/evidence/validation-rerun/env-baseline.md

  Scenario: Unsafe environment detected
    Tool: Bash
    Steps: Inspect env/compose state; if DB target cannot be proven isolated, stop workflow and record the blocker.
    Expected: No destructive command runs; blocker is written to evidence.
    Evidence: .sisyphus/evidence/validation-rerun/env-baseline-blocked.md
  ```

  **Commit**: NO | Message: `n/a` | Files: none

- [ ] 2. Create minimal validation helpers for random sampling and company-scoped reset/delete

  **What to do**: Add the smallest possible execution support needed for this workflow: one helper/management command to sample 50 alive-homepage companies without replacement and persist sampled IDs for the run, and one helper/command path to reset company discovery fields plus delete `JobPosting` rows only for the sampled companies. Include a run identifier or timestamped evidence mapping so counts are attributable by iteration.
  **Must NOT do**: Do not create a generalized framework, do not touch companies outside the sampled set, and do not rely on global deletes.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: destructive-data tooling must be exact and scoped
  - Skills: `[]` - minimal bespoke repo change
  - Omitted: `['review-work']` - final verification wave handles review

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 3,4,5,6,7,8 | Blocked By: 1

  **References**:
  - Pattern: `api/management/commands/rerun_company_crawl_range.py` - scoped reset behavior for company fields
  - Pattern: `api/tasks.py` - discovery/collector task entrypoints and company-range filtering
  - API/Type: `api/models.py` - `Company`, `JobPosting`, discovery-state fields
  - Pattern: `crawler/crawler/spiders/job_collector.py` - posting persistence/upsert behavior

  **Acceptance Criteria**:
  - [ ] Helper can output exactly 50 sampled company IDs from the alive-homepage pool, or fewer with explicit pool-exhaustion evidence.
  - [ ] Reset/delete logic affects only sampled company IDs.
  - [ ] A dry-run or before/after count proves `JobPosting` deletion is company-scoped.

  **QA Scenarios**:
  ```
  Scenario: Sample and scoped delete succeed
    Tool: Bash
    Steps: Run the helper in dry-run/sample mode; capture sampled company IDs; execute reset/delete for one validation batch; query before/after counts for sampled vs non-sampled companies.
    Expected: Sample contains only alive-homepage companies; sampled companies lose prior postings/discovery state; non-sampled companies remain unchanged.
    Evidence: .sisyphus/evidence/validation-rerun/task-2-sample-reset.md

  Scenario: Scope leak attempt
    Tool: Bash
    Steps: Intentionally compare a control company outside the sampled set before and after reset/delete.
    Expected: Control company fields and posting counts are unchanged.
    Evidence: .sisyphus/evidence/validation-rerun/task-2-scope-guard.md
  ```

  **Commit**: YES | Message: `feat(validation): add scoped rerun helpers for sampled companies` | Files: helper/management command paths only

- [ ] 3. Validate Docker startup and capture service readiness evidence

  **What to do**: Run the documented Docker startup flow for the validation environment, confirm app/worker/db/redis readiness, and save logs relevant to the validation run. Capture startup evidence before any data mutation.
  **Must NOT do**: Do not proceed to sampling if required services are unhealthy or repeatedly restarting.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: command execution and evidence capture
  - Skills: `[]` - no extra skill required
  - Omitted: `['git-master']` - still pre-git

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 4,5,6,7,8 | Blocked By: 2

  **References**:
  - Pattern: `README.md` - `docker compose build`, `docker compose up -d`, `docker compose logs`
  - Pattern: `.sisyphus/drafts/project-handoff-summary.md` - runtime commands and expectations

  **Acceptance Criteria**:
  - [ ] Service status evidence shows required services up.
  - [ ] App and worker logs are saved for the validation start window.
  - [ ] Any startup failure stops the workflow with evidence.

  **QA Scenarios**:
  ```
  Scenario: Services start cleanly
    Tool: Bash
    Steps: Run documented Docker startup commands; capture `docker compose ps` and app/worker logs; save readiness evidence.
    Expected: Required services are up and logs do not show fatal startup errors.
    Evidence: .sisyphus/evidence/validation-rerun/task-3-docker-startup.md

  Scenario: Startup failure path
    Tool: Bash
    Steps: Inspect service status/logs after startup; if any critical service is unhealthy, stop and record the failure.
    Expected: No validation loop begins while a required service is unhealthy.
    Evidence: .sisyphus/evidence/validation-rerun/task-3-docker-failure.md
  ```

  **Commit**: NO | Message: `n/a` | Files: none

- [ ] 4. Execute the bounded random-batch rerun loop with attributable counters

  **What to do**: Run validation iterations over random batches of 50 alive-homepage companies, without replacement across the session, using the scoped helper from Task 2. For each iteration: freeze sampled IDs, record pre-reset counts, reset discovery state, delete postings for sampled companies, rerun discovery and job collection, wait for queues/processes to drain, then record post-rerun counts. Stop once recollected company `recruits_url` count exceeds 20 and recollected `JobPosting` row count exceeds 30. Use a hard cap of 5 iterations or 8 hours, whichever comes first.
  **Must NOT do**: Do not use global table counts, do not overlap iterations, and do not silently resample the same companies before pool exhaustion.

  **Recommended Agent Profile**:
  - Category: `deep` - Reason: multi-iteration orchestration with destructive state transitions
  - Skills: `[]` - repo-specific flow dominates
  - Omitted: `['review-work']` - review happens later

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 5,6,7,8 | Blocked By: 3

  **References**:
  - Pattern: `api/tasks.py` - `run_discover_careers_spiders*`, `run_job_collector_spiders*`
  - Pattern: `api/management/commands/rerun_company_crawl_range.py` - reset-then-rerun structure
  - API/Type: `api/models.py` - company/posting fields to count and verify

  **Acceptance Criteria**:
  - [ ] Every iteration writes sampled IDs and pre/post counters to evidence.
  - [ ] No sampled company appears twice before pool exhaustion.
  - [ ] Threshold success or bounded-stop failure is explicitly recorded.

  **QA Scenarios**:
  ```
  Scenario: Threshold reached within bounds
    Tool: Bash
    Steps: Run iteration loop; after each iteration, query sampled companies for non-empty `recruits_url` and `JobPosting` count; save counters.
    Expected: Workflow stops when recruit-page recollection > 20 and posting recollection > 30; evidence shows the winning iteration.
    Evidence: .sisyphus/evidence/validation-rerun/task-4-iterations.md

  Scenario: Threshold not reached
    Tool: Bash
    Steps: Continue until 5 iterations or 8 hours are reached without satisfying thresholds.
    Expected: Workflow stops cleanly, records failure reason, and does not continue indefinitely.
    Evidence: .sisyphus/evidence/validation-rerun/task-4-bounded-stop.md
  ```

  **Commit**: NO | Message: `n/a` | Files: none

- [ ] 5. Materialize validation sample sets for manual QA

  **What to do**: From the successful iteration, choose 10 recollected recruit pages and 10 recollected job postings for manual QA. Use a deterministic random seed or explicit ordered selection recorded in evidence. Ensure company IDs, URLs, and relevant identifiers are frozen before inspection.
  **Must NOT do**: Do not cherry-pick only obvious successes without recording the selection rule.

  **Recommended Agent Profile**:
  - Category: `quick` - Reason: deterministic sample extraction and evidence writing
  - Skills: `[]` - no extra skill required
  - Omitted: `['dev-browser']` - browser comes in the next task

  **Parallelization**: Can Parallel: NO | Wave 2 | Blocks: 6,7,8 | Blocked By: 4

  **References**:
  - Pattern: `api/views_jobs.py` - how postings are surfaced and identified
  - API/Type: `api/models.py` - source identifiers for companies/postings
  - Pattern: `.sisyphus/drafts/project-handoff-summary.md` - API/job endpoint summary

  **Acceptance Criteria**:
  - [ ] Exactly 10 recruit pages and 10 job postings are selected and listed.
  - [ ] Selection method is reproducible and written to evidence.
  - [ ] All selected records come from the successful threshold iteration.

  **QA Scenarios**:
  ```
  Scenario: Deterministic QA sample created
    Tool: Bash
    Steps: Query successful-iteration results; select 10 recruit pages and 10 job postings using a fixed seed or explicit order; write the manifest.
    Expected: The same query/seed reproduces the same QA sample set.
    Evidence: .sisyphus/evidence/validation-rerun/task-5-qa-samples.md

  Scenario: Invalid sample source rejected
    Tool: Bash
    Steps: Attempt to include records outside the successful iteration; compare IDs against iteration manifest.
    Expected: Out-of-scope records are rejected and the manifest remains clean.
    Evidence: .sisyphus/evidence/validation-rerun/task-5-sample-guard.md
  ```

  **Commit**: NO | Message: `n/a` | Files: none

- [ ] 6. Capture browser evidence and evaluate 10 recruit pages + 10 postings

  **What to do**: Open each selected recruit page and job posting using browser automation, save screenshots/HTML or equivalent immutable evidence, then evaluate each item with a fixed rubric: page loads, page is truly a recruit page or job posting, company/page match is correct, and extracted posting content is coherent with the source page. Save all evidence paths and findings.
  **Must NOT do**: Do not rely on unsaved “visual confirmation,” and do not copy sensitive or excessive page content into git unnecessarily.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: manual-QA evidence capture with browser tooling
  - Skills: [`playwright`] - browser automation and screenshots
  - Omitted: `[]` - none

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 7,8 | Blocked By: 5

  **References**:
  - Pattern: `/playwright` skill - required browser evidence capture workflow
  - Pattern: `README.md` and runbook docs - endpoints and service access context
  - Pattern: `api/views_jobs.py` - posted data shape to compare against source pages

  **Acceptance Criteria**:
  - [ ] Evidence exists for all 20 reviewed items.
  - [ ] Each reviewed item has a rubric result: pass/fail/uncertain with rationale.
  - [ ] At least one failure/edge-case example is documented if any is found.

  **QA Scenarios**:
  ```
  Scenario: Recruit/job samples reviewed with evidence
    Tool: Playwright
    Steps: Visit each sampled URL; capture screenshot and HTML/text evidence; compare page meaning with stored recruit/job data; write rubric outcomes.
    Expected: All 20 items have saved evidence and a binary/ternary verdict.
    Evidence: .sisyphus/evidence/validation-rerun/task-6-manual-qa.md

  Scenario: Broken or blocked page
    Tool: Playwright
    Steps: Visit a sampled URL that fails to load or redirects unexpectedly.
    Expected: Failure is recorded with screenshot, status details, and marked against validation quality.
    Evidence: .sisyphus/evidence/validation-rerun/task-6-manual-qa-failure.md
  ```

  **Commit**: NO | Message: `n/a` | Files: none

- [ ] 7. Write the docs validation report and assemble push candidate diff

  **What to do**: Create `docs/validation/2026-04-20-random-rerun-validation.md` summarizing environment safety, iteration history, thresholds, sampled QA items, findings, limitations, and a clear push recommendation. Keep raw bulky artifacts outside tracked docs if `.gitignore` requires; link to evidence paths instead. Prepare the exact git diff intended for push and exclude secrets/log/data noise.
  **Must NOT do**: Do not include `.env`, raw logs, generated exports, or unrelated file changes in the push candidate.

  **Recommended Agent Profile**:
  - Category: `writing` - Reason: evidence-backed technical reporting
  - Skills: `[]` - no extra skill required
  - Omitted: `['git-master']` - push happens only after approval

  **Parallelization**: Can Parallel: YES | Wave 3 | Blocks: 8 | Blocked By: 6

  **References**:
  - Pattern: `docs/RUNBOOK.md` - operational reporting style
  - Pattern: `.sisyphus/drafts/project-handoff-summary.md` - concise technical summary style
  - Pattern: `.sisyphus/evidence/validation-rerun/` - evidence sources to cite

  **Acceptance Criteria**:
  - [ ] Report file exists at the exact docs path.
  - [ ] Report cites thresholds, iterations, QA findings, and explicit limitations.
  - [ ] Proposed git diff excludes secrets/noisy artifacts.

  **QA Scenarios**:
  ```
  Scenario: Final report is evidence-backed
    Tool: Bash
    Steps: Generate report markdown; verify linked evidence files exist; inspect git diff for included paths.
    Expected: Report is complete and git diff is limited to intentional docs/code changes only.
    Evidence: .sisyphus/evidence/validation-rerun/task-7-report-check.md

  Scenario: Noisy artifact exclusion
    Tool: Bash
    Steps: Check git status/diff for logs, exports, `.env`, or unrelated generated files.
    Expected: No disallowed artifact is included in the push candidate.
    Evidence: .sisyphus/evidence/validation-rerun/task-7-diff-guard.md
  ```

  **Commit**: YES | Message: `docs(validation): record random rerun verification results` | Files: docs report + minimal helper changes if approved for commit

- [ ] 8. Present results, get explicit approval, then push

  **What to do**: Present the final report path, evidence summary, and exact commit/push candidate to the user. Wait for explicit approval. After approval, create any remaining commit(s) and push the approved branch to its configured remote.
  **Must NOT do**: Do not push before approval, and do not force-push.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` - Reason: approval-gated release step with repo hygiene
  - Skills: [`git-master`] - safe staging/commit/push discipline
  - Omitted: `[]` - none

  **Parallelization**: Can Parallel: NO | Wave 3 | Blocks: F1,F2,F3,F4 | Blocked By: 7

  **References**:
  - Pattern: current branch and remote config from git metadata
  - Pattern: final report `docs/validation/2026-04-20-random-rerun-validation.md`
  - Pattern: `.sisyphus/evidence/validation-rerun/` - approval evidence basis

  **Acceptance Criteria**:
  - [ ] User approval is explicitly recorded in the session before push.
  - [ ] Push succeeds without force options.
  - [ ] Post-push status confirms a clean working tree or only approved residual artifacts.

  **QA Scenarios**:
  ```
  Scenario: Approval-gated push succeeds
    Tool: Bash
    Steps: Show report/evidence summary; wait for explicit user okay; stage approved files; commit; push; record post-push status.
    Expected: Push occurs only after approval and completes successfully.
    Evidence: .sisyphus/evidence/validation-rerun/task-8-push.md

  Scenario: Approval withheld
    Tool: Bash
    Steps: Present report and do not execute push until user approves.
    Expected: Repository remains unpushed while awaiting approval.
    Evidence: .sisyphus/evidence/validation-rerun/task-8-awaiting-approval.md
  ```

  **Commit**: YES | Message: `chore(validation): push approved rerun verification changes` | Files: approved staged files only

## Final Verification Wave (MANDATORY — after ALL implementation tasks)
> 4 review agents run in PARALLEL. ALL must APPROVE. Present consolidated results to user and get explicit "okay" before completing.
> **Do NOT auto-proceed after verification. Wait for user's explicit approval before marking work complete.**
> **Never mark F1-F4 as checked before getting user's okay.** Rejection or user feedback -> fix -> re-run -> present again -> wait for okay.
- [ ] F1. Plan Compliance Audit — oracle
- [ ] F2. Code Quality Review — unspecified-high
- [ ] F3. Real Manual QA — unspecified-high (+ playwright if UI)
- [ ] F4. Scope Fidelity Check — deep

## Commit Strategy
- Commit helper code separately from the final validation report if helper implementation is required.
- Do not commit raw logs, exports, `.env`, DB dumps, or bulky evidence artifacts unless explicitly requested.
- Push only after the user approves the report and the final diff.

## Success Criteria
- Validation environment safety is proven before any destructive step.
- Random sampled rerun loop is reproducible and bounded.
- Recollection thresholds are met or bounded failure is documented with evidence.
- Manual QA evidence exists for 10 recruit pages and 10 postings.
- Final docs report is written and approved.
- Push happens only after explicit approval.
