# GPT Parser Setup

구인페이지 분석/파싱/저장은 기본적으로 기존 로컬·룰 기반 fallback으로 동작한다. GPT 기반 구조화 추출은 선택 기능이며, 개발 계정으로 먼저 테스트한 뒤 실서비스 계정으로 교체할 수 있게 환경변수로만 제어한다.

## ChatGPT Plus 계정과 OpenAI API

ChatGPT Plus 로그인만으로는 서버 코드에서 OpenAI API를 호출할 수 없다. 이 프로젝트의 GPT parser는 OpenAI API SDK를 사용하므로 `OPENAI_API_KEY`가 필요하다.

- ChatGPT Plus: chatgpt.com 웹/앱 구독.
- OpenAI API: platform.openai.com에서 API key를 발급하고 사용량 기반 과금/한도 관리를 하는 별도 API 사용 경로.
- 같은 OpenAI 계정으로 Platform에 들어갈 수는 있지만, API key와 billing/usage 설정은 별도로 준비해야 한다.

## OPENAI_PROJECT란?

`OPENAI_PROJECT_ID`는 OpenAI Platform에서 사용량/권한/키를 분리 관리할 때 쓰는 project 식별자다. 필수는 아니며, 단일 기본 프로젝트로 테스트할 때는 비워도 된다. 기존 호환을 위해 `OPENAI_PROJECT`도 읽지만, 새 설정은 `OPENAI_PROJECT_ID`를 우선 사용한다.

만드는 위치:

1. `https://platform.openai.com/` 접속
2. 로그인
3. Settings/Projects 영역에서 project 생성 또는 기본 project 확인
4. API Keys에서 해당 project에 연결된 key 발급
5. 필요한 경우 project id를 `OPENAI_PROJECT_ID`에 입력

프로젝트를 비워도 API key 자체가 유효하면 기본 project/조직 컨텍스트로 호출된다. 운영에서는 비용/권한 추적을 위해 개발 project와 production project를 분리하는 것을 권장한다.

## 동작 방식

1. `crawler/crawler/spiders/job_collector.py`가 채용 상세/원페이지 텍스트를 읽는다.
2. `api.llm_parser.parse_job_details_with_llm()`를 호출한다.
3. `OPENAI_PARSER_ENABLED=1`이고 `OPENAI_API_KEY`가 있으면 OpenAI 파서를 먼저 호출한다.
4. GPT가 반환한 구조화 필드를 정리한다.
5. 비어 있거나 실패한 값은 기존 날짜/급여/섹션/지역/고용형태 fallback이 보완한다.
6. 최종 결과는 기존 `JobPosting` upsert 로직으로 저장된다.

## 개발 계정 테스트

개발 환경의 `.env` 또는 secret에만 넣는다.

```env
OPENAI_PARSER_ENABLED=1
OPENAI_API_KEY=development_openai_key
OPENAI_PROJECT_ID=development_project_id  # optional; blank is OK for a simple first smoke test
OPENAI_PROJECT=  # legacy alias; leave blank for new setups
OPENAI_ORGANIZATION=
OPENAI_MODEL=gpt-4o-mini
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_RETRIES=2
```

반영 후 app/worker를 재시작한다.

```bash
docker compose up -d --force-recreate app worker
```

## 실서비스 계정 전환

코드는 변경하지 않는다. 배포 secret에서 같은 변수명에 production key/project를 주입한다.

- 개발 key와 production key를 같은 컨테이너/프로세스에 동시에 넣지 않는다.
- 실제 key를 git, 문서, 이슈, 로그, 스크린샷에 남기지 않는다.
- key 변경 후 app/worker를 재시작한다.
- 비용 관리를 위해 `OPENAI_MODEL`, worker concurrency, `OPENAI_TIMEOUT_SECONDS`, `OPENAI_MAX_RETRIES`를 운영 환경에서 명시한다.

실서비스 입력 위치:

- 로컬/단일 Docker 개발: `.env`
- 운영 배포: Docker/CI/서버 secret manager 또는 배포 환경변수

실제 key는 `.env.example`, `.env.template`, 문서, git commit에 넣지 않는다.

## 비활성화

```env
OPENAI_PARSER_ENABLED=0
```

이 상태에서는 OpenAI key가 있어도 GPT 파서를 쓰지 않고 기존 fallback만 사용한다.

## API 테스트 페이지에서 확인

브라우저에서 아래 페이지를 연다.

```text
http://localhost:8200/api-test/
```

`GPT/job parser test` 카드의 `POST /api/parse/job/` 버튼은 DB 저장 없이 GPT/OpenAI parser 설정과 smoke-test 상태를 확인한다. 이 테스트는 무거운 로컬 zero-shot fallback 모델을 로드하지 않는다.

테스트 페이지에는 OpenAI key 입력칸을 두지 않는다. 개발 key는 `.env` 또는 container secret에 넣고 app/worker를 재생성한다.

```env
OPENAI_PARSER_ENABLED=1
OPENAI_API_KEY=development_openai_key
OPENAI_PROJECT_ID=development_project_id  # optional
OPENAI_MODEL=gpt-4o-mini
```

```bash
docker compose up -d --force-recreate app worker
```

그 다음 `GPT/job parser test` 카드에서 `POST /api/parse/job/`를 누르면 서버에 설정된 key로 실제 GPT 호출을 시도한다.

실제 URL을 가지고 테스트하려면 `실제 URL에서 visible text 가져와 파싱하기(fetch_url=true)`를 체크하거나 `Use URL fetch example` 버튼을 누른다. 이 경우 서버가 public `http/https` URL을 직접 요청하고 HTML visible text를 추출한 뒤 GPT parser에 전달한다. localhost/private/link-local 주소와 비텍스트 응답은 안전상 거부한다.

응답의 `parser_config`를 보면 현재 app 컨테이너 기준 설정을 확인할 수 있다.

```json
{
  "parser_config": {
    "openai_parser_enabled": true,
    "openai_api_key_configured": true,
    "openai_project_configured": true,
    "openai_model": "gpt-4o-mini"
  },
  "parsed": {},
  "saved": false
}
```

- `openai_parser_enabled=false`이면 `.env`의 `OPENAI_PARSER_ENABLED=1` 설정이 app/worker에 반영되지 않은 것이다.
- `openai_api_key_configured=false`이면 `OPENAI_API_KEY`가 비어 있는 것이다.
- 둘 중 하나가 false이면 `parsed`는 비어 있고 `skipped_reason`에 설정 누락 사유가 표시된다.
- `smoke_status=configuration_only`이면 실제 OpenAI API 호출은 하지 않은 상태다.
- `smoke_status=real_openai_call_attempted`이면 현재 app 컨테이너가 OpenAI API 호출을 시도한 상태다.
- `source.fetched=true`이면 URL fetch와 visible text 추출이 성공한 상태다.
- 실제 GPT 응답까지 확인하려면 `smoke_status=real_openai_call_attempted`이고 `parsed`에 구조화 필드가 채워지는지 본다.
- 설정 변경 후에는 `docker compose up -d --force-recreate app worker`로 재시작한다.
