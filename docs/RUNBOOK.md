# RUNBOOK — Job Crawler Full Template

## 0. 기본 원칙
- “코드 수정” 후 반영 방식은 두 가지다.
  1) 컨테이너가 소스 볼륨을 물고 있으면(현재 구성) 대부분 즉시 반영.
  2) 단, `.env` 변경 / 의존성 변경 / 이미지 빌드 변경은 재시작/재빌드 필요.

---

## 1. 부팅/재시작
### 기본 기동
bash
docker compose up -d
docker compose ps



로그 보기
docker compose logs -f app --tail=200
docker compose logs -f worker --tail=200
docker compose logs -f beat --tail=200


.env 변경 반영(키 누락 방지)
docker compose up -d --force-recreate worker beat

2. 마이그레이션
docker compose exec app python manage.py makemigrations
docker compose exec app python manage.py migrate

3. Django Admin 접속

API/관리:

http://localhost:8200/admin/

스케줄 확인:

http://localhost:8200/admin/django_celery_beat/periodictask/

4. “지금 동작이 끝났나?” 확인
Celery worker 상태
docker compose exec worker celery -A config inspect ping
docker compose exec worker celery -A config inspect active
docker compose exec worker celery -A config inspect reserved

Company 카운트
docker compose exec app python manage.py shell -c "from api.models import Company; print('companies=', Company.objects.count())"

DART 보강 정도(상장사 카운트)
docker compose exec app python manage.py shell -c "from api.models import Company; print('stock_code=', Company.objects.exclude(stock_code__isnull=True).exclude(stock_code='').count())"


5. 수동 실행(자주 쓰는 것)

Windows에서는 여러 줄 \ 쓰지 말고 한 줄로 실행.

5.1 OSM 수집
docker compose exec app python manage.py shell -c "from api.tasks import collect_osm_companies; collect_osm_companies.delay(regions=['서울특별시'], mode='medium', limit=50); print('queued')"

5.2 SWDB 수집(CSV 또는 API 설정 필요)
docker compose exec app python manage.py shell -c "from api.tasks import collect_swdb_companies; collect_swdb_companies.delay(regions=[], limit=None, only_with_homepage=True); print('queued')"

5.3 DART 수집(상장사 신규 생성/변경분)
docker compose exec app python manage.py shell -c "from api.tasks import collect_dart_companies; collect_dart_companies.delay(regions=[], mode='discover_listed', since_days=365, limit=None, only_with_homepage=True); print('queued')"

6. 홈페이지 dead 체크(테스트/운영)
테스트: 30개만
docker compose exec app python manage.py shell -c "from api.tasks import check_company_homepages; r=check_company_homepages.delay(limit=30, skip_recent_days=0); print('task_id=', r.id)"

최근 체크된 샘플 10개 보기
docker compose exec app python manage.py shell -c "from api.models import Company; qs=Company.objects.exclude(homepage_checked_at__isnull=True).order_by('-homepage_checked_at').values_list('name','homepage_url','homepage_url_status','homepage_last_status_code','homepage_fail_count','homepage_checked_at')[:10]; print(list(qs))"

dead 개수
docker compose exec app python manage.py shell -c "from api.models import Company; print('dead=', Company.objects.filter(homepage_url_status='dead').count())"

운영: 전체 돌리기(운영 PC 권장)

limit=None 또는 큰 값으로 chunk 처리하는 정책을 사용.

사양 낮은 노트북에서는 비추천.

7. 스케줄(주기 작업) 등록/갱신
코드 기반 스케줄 업서트(있다면)
docker compose exec app python manage.py shell -c "from api.tasks import setup_company_seed_schedules; setup_company_seed_schedules.delay(); print('queued')"

스케줄이 제대로 들어갔는지

Admin 페이지에서 PeriodicTask 목록 확인.

task name / crontab / kwargs 확인.

8. DB 초기화/재시딩(주의)

운영에서 함부로 하지 말 것.

방법 A: DB 볼륨 삭제(완전 초기화)
docker compose down -v
docker compose up -d
docker compose exec app python manage.py migrate

방법 B: Company만 비우기(관계 모델 주의)
docker compose exec app python manage.py shell -c "from api.models import Company; Company.objects.all().delete(); print('deleted')"

9. 트러블슈팅 빠른 체크

worker가 아무 로그도 안 찍는다

celery inspect active/reserved로 실제 큐 소비 중인지 확인.

.env 수정 후 worker/beat 재생성 필요할 수 있음.

DART 키 missing

.env에 OPENDART_API_KEY 확인.

--force-recreate worker beat.

Windows에서 shell -c 명령이 SyntaxError

한 줄로 실행.

따옴표 중첩 깨지면 작은따옴표/큰따옴표를 바꿔서 시도.