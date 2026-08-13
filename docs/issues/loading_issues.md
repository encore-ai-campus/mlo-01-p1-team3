# Loading 구현 모듈 이슈 보고서

- 작성일: 2026-08-13
- 갱신일: 2026-08-13
- 대상 저장소: `/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3`
- 대상 모듈: `src/loading`
- 참고 폴더: `/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/ref/mlo-01-p1-team3-a`
- 목적: 현재 계약상 정상 동작을 승인하기 위해 반드시 확인·확정해야 하는 loading 구현 이슈를 우선순위별로 보고
- 이번 갱신 범위: 실제 소스·테스트·Git 추적 상태를 재확인하여 현재 판정·증거·잔여 조건을 갱신함. 결정사항 원문은 작성하지 않음

## 0. 결정 반영 상태

본 보고서의 결정사항 자체는 기입하지 않는다. 아래의 현재 상태만 실제 구현·테스트·Git 상태에 따라 갱신한다.

| ID | 결정 및 현재 상태 |
|---|---|
| LOAD-001 | 수정 반영 완료. SQL unchanged write 생략 및 회귀 테스트 통과 |
| LOAD-002 | 수정 반영 완료. Mongo validator 선행 전제와 migration 구현 확인. 실제 MongoDB smoke test는 미실행 |
| LOAD-003 | 수정 반영 완료. driver·migration이 현재 HEAD에 추적됨. 실제 DB migration/smoke test와 원격 브랜치 반영은 별도 확인 |
| LOAD-004 | 수정 반영 완료. SQL checkpoint·동일 transaction 기록·incremental fail-closed 구현 확인. 실제 DB smoke test는 미실행 |
| LOAD-005 | 수정 반영 완료. FAQ·등록현황 입력 검증 및 회귀 테스트 통과 |
| LOAD-006 | 수정 반영 완료. 테스트·migration이 현재 HEAD에 추적되고 loading 14개·전체 80개 테스트 통과 |
| LOAD-007 | 결정/운영 전제 대기. 이번 수정 범위에서 제외 |

## 1. 판정 기준

| 우선순위 | 의미 |
|---|---|
| P0 | 테스트 또는 실행 환경이 확보되지 않아 정상 실행을 승인할 수 없는 차단 이슈 |
| P1 | 정상 fixture 경로는 실행될 수 있으나 계약 이행·재현 가능한 검수·운영 안전성을 위해 반드시 해소해야 하는 이슈 |
| P1-조건부 | 실제 DB·상위 호출자·운영 source 계약을 확인한 뒤 승격 여부를 결정할 이슈 |
| P2 | 정상 경로를 즉시 차단하지 않지만 방어력·동시성·문서 정합성을 저해하는 이슈 |

## 2. 요약

현재 `src/loading`에는 JSONL 원자적 쓰기, business key 기반 Upsert, SQL 참조 테이블 FK 순서, unchanged write 생략, 입력 계약 검증, SQL transaction·rollback, SQL checkpoint 기록이 구현되어 있다. 연관 `src/pipelines/usedcar.py`에도 incremental fail-closed 경로가 반영되어 있다.

현재 로컬 HEAD `7a88f55` 기준 loading 전용 테스트 14개와 전체 테스트 80개가 통과한다. SQL·Mongo migration 6개 파일도 현재 HEAD에 추적되어 있으므로 clean checkout에서 migration import와 loading contract test를 재현할 수 있는 파일 추적 조건은 충족했다. 다만 실제 MySQL/MongoDB 연결·migration 적용·upsert smoke test는 실행하지 않았고, 원격 `origin/fix/validate-pipeline` ref는 아직 `2d8103e`를 가리키므로 원격 반영 여부는 별도 확인이 필요하다.

| ID | 우선순위 | 모듈 | 이슈 | 현재 판정 |
|---|---|---|---|---|
| LOAD-001 | P1 | `usedcar.py`, `registration.py` | unchanged 재실행 시 SQL write·load-owned timestamp 갱신 | 해소. SQL unchanged write 생략 테스트 통과 |
| LOAD-002 | P1-조건부 | `faq.py`, Mongo migration | FAQ MongoDB validator 및 index 계약 | 코드·migration 전제 반영. 실제 MongoDB smoke test 미실행 |
| LOAD-003 | P1-조건부 | migration·requirements | clean checkout에서 SQL/MongoDB 경로 재현 | 해소. driver·migration이 HEAD에 추적됨. 실제 DB/원격 반영은 미검증 |
| LOAD-004 | P1-조건부 | `SqlUpsertSink`, pipeline·checkpoint | 운영 progress key 및 incremental fail-closed 계약 | 코드·contract test 반영. 실제 DB smoke test 미실행 |
| LOAD-005 | P2 | FAQ·registration sink | 직접 호출 입력 검증이 준비 계약보다 약함 | 해소. 입력 검증 및 회귀 테스트 통과 |
| LOAD-006 | P1 | loading 테스트·Git 상태 | 단위 테스트 증거와 Git 추적 상태 | 해소. 현재 HEAD에서 테스트·migration 추적 및 14/80 통과 확인 |
| LOAD-007 | P2-조건부 | JSON quota·state·checkpoint | atomic file write는 있으나 다중 프로세스 경합 보호 없음 | 보류. 이번 수정에서 제외 |

### 확인된 정상 경로

- [src/loading/common.py:10](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/common.py:10)의 임시 파일 작성 후 `os.replace`하는 원자적 쓰기 구조가 확인되었다.
- JSONL FAQ·중고차·등록현황 sink와 SQL 중고차·등록현황 sink는 business key를 기준으로 신규·변경·unchanged를 분류하고 unchanged write를 건너뛴다.
- [src/loading/usedcar.py:583](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/usedcar.py:583)은 중고차 참조 테이블을 먼저 저장한 뒤 listing을 저장하며, [src/loading/usedcar.py:655](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/usedcar.py:655)의 transaction commit/rollback 경로가 존재한다.
- [src/loading/faq.py:150](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/faq.py:150)는 MongoDB collection validator를 확인한 뒤 index와 Upsert를 수행한다.
- [src/loading/usedcar.py:397](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/usedcar.py:397)는 최신 성공 SQL `progress_key`를 읽고, [src/loading/usedcar.py:431](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/usedcar.py:431)는 적재와 같은 transaction에 성공 기록을 포함한다.
- SQL 값은 파라미터 바인딩을 사용하고 loading 계층은 collection·preprocessing·pipeline을 직접 import하지 않는다.
- 현재 Conda `sandbox`에서 `python -m pytest -q tests/test_loading_time_contract.py`는 `14 passed`, `python -m pytest -q`는 `80 passed`이며 `compileall`과 `ruff check`도 통과했다.
- 현재 HEAD `7a88f55`에는 loading source·README·requirements·test와 SQL/Mongo migration이 모두 추적되어 있다.

---

## LOAD-001. SQL unchanged 재실행 안정성

### 우선순위

**P1 — 수정 반영 완료. 실제 DB 이중 실행 검증은 별도 확인 조건**

### 관련 계약 및 구현

참조 데이터 명세는 `created_at`을 최초 저장 시 유지하고, `updated_at`을 실제 변경 시 갱신하도록 정의한다.

- [참조 Data Specification:47-48](</Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/ref/mlo-01-p1-team3-a/docs/05_Data Specification.md:47>)

현재 구현은 기존 행을 조회한 뒤 business/source 필드를 비교하고, `insert`와 `update`만 SQL write 대상으로 남긴다.

- [src/loading/usedcar.py:319](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/usedcar.py:319): `_partition_rows()`가 신규·변경·unchanged를 분류한다.
- [src/loading/usedcar.py:583](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/usedcar.py:583): FK 순서로 변경·신규 dimension과 listing만 `executemany()` 한다.
- [src/loading/registration.py:420](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/registration.py:420): 등록현황도 `write_records`만 SQL write 대상으로 만든다.
- [src/loading/usedcar.py:230](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/usedcar.py:230): omitted 값은 `COALESCE`로 기존 non-null 값을 보존한다.

### 확인 결과

현재 대상 저장소의 `tests/test_loading_time_contract.py`에서 fake SQL connection으로 동일 레코드를 재실행하여 다음을 확인한다.

    test_sql_usedcar_unchanged_rows_are_not_written: passed
    test_sql_registration_unchanged_rows_are_not_written: passed
    unchanged_count = 1
    executemany_calls = []

### 영향

- unchanged SQL row를 다시 쓰지 않으므로 `updated_at`, `run_id`, `collected_at`을 불필요하게 갱신하지 않는다.
- `unchanged_count`와 실제 SQL write 생략 결과가 일치한다.
- changed/new row에만 loading timestamp를 적용하며 `created_at`은 기존 값을 보존한다.

### 현재 판정 및 잔여 확인

코드와 fake SQL contract test 기준으로 이슈는 해소되었다. 실제 MySQL에서 같은 batch를 두 번 실행하여 row 값·timestamp·write 횟수를 확인하는 smoke test는 실행하지 않았으므로 운영 DB 검증 완료로 확대하지 않는다.

---

## LOAD-002. FAQ MongoDB validator 계약

### 우선순위

**P1-조건부 — 코드·migration 전제 반영 완료. 실제 MongoDB 초기화 smoke test는 미실행**

### 관련 계약 및 구현

참조 loading README는 FAQ MongoDB에 대해 validator와 index 확인을 요구한다.

- [참조 loading README:13](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/ref/mlo-01-p1-team3-a/src/loading/README.md:13)

참조 migration에는 FAQ 필수 필드와 타입을 검사하는 validator가 있다.

- [참조 Mongo migration:47](</Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/ref/mlo-01-p1-team3-a/migrations/mongo/ensure_indexes.py:47>)

현재 FAQ sink는 초기화 시 collection 존재와 validator 설정을 확인하고, validator가 없으면 실패한다. validator가 준비된 뒤 세 index를 생성한다.

- [src/loading/faq.py:150](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/faq.py:150): `_ensure_validator()`가 Mongo collection validator를 확인한다.
- [src/loading/faq.py:163](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/faq.py:163): 저장 직전에 FAQ prepared document를 검증한다.
- [src/loading/faq.py:145](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/faq.py:145): validator 확인 후 unique·조회 index를 보장한다.
- [migrations/mongo/ensure_indexes.py:21](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/migrations/mongo/ensure_indexes.py:21): validator와 세 index를 생성·보정하는 migration 구현이 현재 HEAD에 추적되어 있다.
- [src/loading/README.md:128](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/README.md:128): migration 선행 조건과 sink 초기화 계약이 문서화되어 있다.

### 영향

- validator가 없는 collection을 sink가 자동으로 정상 처리하지 않으므로 schema 전제 누락을 조기에 알린다.
- FAQ 입력은 loading 내부에서도 필수 필드·URL·timestamp·boolean 계약을 확인한다.
- migration이 선행된 환경을 외부 계약으로 명시했으며, migration 파일의 Git 추적 여부는 LOAD-003에서 별도로 판정한다.

### 현재 판정 및 잔여 확인

validator를 별도 migration이 준비하고 sink가 이를 필수 전제로 확인하는 방식으로 구현·문서화했으며 migration 파일은 현재 HEAD에 추적되어 있다. 현재 contract test는 validator 필수 필드와 sink 입력 검증을 확인하지만, 실제 MongoDB에서 빈 collection 생성·기존 collection `collMod`·index·Upsert를 실행한 증거는 없다.

---

## LOAD-003. clean checkout에서 SQL·MongoDB 경로 재현성

### 우선순위

**P1-조건부 — 수정 반영 완료. 실제 DB migration/smoke test와 원격 브랜치 반영은 미검증**

### 확인된 내용

현재 loading README는 저장소 루트 migration을 참조하고, [requirements.txt:6-7](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/requirements.txt:6)에 loading과 migration이 사용하는 `PyMySQL`·`pymongo`를 선언한다.

현재 HEAD `7a88f55`에는 다음 migration 구현이 추적되어 있다.

- [migrations/sql/V001__mvp_schema.sql](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/migrations/sql/V001__mvp_schema.sql)
- [migrations/sql/run.py](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/migrations/sql/run.py)
- [migrations/mongo/ensure_indexes.py](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/migrations/mongo/ensure_indexes.py)

`git ls-files migrations`에서 위 6개 파일이 확인되고, [7a88f55](https://github.com/encore-ai-campus/mlo-01-p1-team3/commit/7a88f55f8aab95253bb2dcfbf9ac8d975e8b394b)의 `chore: add migrations` commit에서 추가되었다. 따라서 현재 로컬 HEAD를 기준으로는 clean checkout에 필요한 migration 파일 추적 조건이 충족되었다. 다만 현재 `origin/fix/validate-pipeline` ref는 `2d8103e`이므로 원격 브랜치에 `7a88f55`가 반영되었는지는 이 checkout에서 확인되지 않는다.

### 영향

- clean checkout에 필요한 `PyMySQL`·`pymongo` dependency 선언과 SQL/Mongo migration 파일이 현재 HEAD에 포함되어 있다.
- migration을 import하는 loading contract test가 현재 HEAD의 파일 집합에서 실행되며, 현재 checkout에서 14개 loading test와 80개 전체 테스트가 통과한다.
- 실제 DB에 migration을 적용하고 schema·validator·index·Upsert를 확인한 것은 아니며, 원격 branch 반영 여부도 별도 상태다.

### 현재 판정 및 잔여 확인

requirements와 loading 소스의 driver 사용은 일치하고, migration 구현은 현재 HEAD에 추적되어 있어 clean checkout 파일 재현성 이슈는 해소되었다. 현재 테스트는 migration splitter와 CLI 도움말 수준의 contract를 확인한다. 실제 DB에 대한 migration 적용·쓰기 검증은 수행하지 않았으므로 DB Upsert 성공으로 보고하지 않으며, 원격 branch 반영은 별도 확인한다.

---

## LOAD-004. 운영 checkpoint 및 incremental fail-closed 계약

### 우선순위

**P1-조건부 — 코드·contract test 반영 완료. 실제 DB/source smoke test는 미실행**

### 관련 계약 및 구현

참조 구현 문서는 source의 `sequence`, `updated_at`, `cursor` 중 하나를 확정하고, 증분 기준값이 없으면 `incremental_contract_missing`으로 중단하도록 요구한다.

- [참조 구현 문서:364](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/ref/mlo-01-p1-team3-a/docs/00_implementation.md:364)
- [참조 구현 문서:370](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/ref/mlo-01-p1-team3-a/docs/00_implementation.md:370)

또한 성공한 SQL batch의 `pipeline_runs.status=SUCCESS`와 `progress_key`를 다음 checkpoint 후보로 기록하도록 정의한다.

- [참조 구현 문서:372](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/ref/mlo-01-p1-team3-a/docs/00_implementation.md:372)
- [참조 구현 문서:383](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/ref/mlo-01-p1-team3-a/docs/00_implementation.md:383)

현재 구현은 local JSON checkpoint를 fallback으로 유지하면서 SQL sink의 성공 `pipeline_runs.progress_key`를 canonical 후보로 읽고, sink 성공 transaction 안에 batch별 성공 기록을 함께 저장한다.

- [src/loading/usedcar.py:397](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/usedcar.py:397): 최신 `SUCCESS` checkpoint 조회
- [src/loading/usedcar.py:431](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/usedcar.py:431): 적재 통계와 `pipeline_runs` 성공 기록 생성
- [src/loading/usedcar.py:646](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/usedcar.py:646): upsert와 checkpoint 기록을 같은 transaction에 포함
- [src/pipelines/usedcar.py:26](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/usedcar.py:26): 증분 page에 `high_water_seq`가 없으면 fail-closed
- [src/pipelines/usedcar.py:159](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/usedcar.py:159): sequence가 있는 경우에만 SQL checkpoint를 전달

### 영향

- SQL sink는 운영 checkpoint를 조회·기록하고, local JSON은 SQL checkpoint가 없을 때의 fallback 역할로 제한된다.
- 증분 mode에서 기준값이 없으면 적재 전에 `incremental_contract_missing`으로 종료한다.
- 초기 mode에서 끝까지 기준값이 없으면 데이터 write 후에도 checkpoint를 전진시키지 않고 동일 오류로 종료한다.
- SQL write 또는 checkpoint statement가 실패하면 전체 transaction을 rollback한다.

### 현재 판정 및 잔여 확인

checkpoint source-of-truth 역할 분리, SQL transaction 결합, 증분 fail-closed 경로가 코드와 README에 반영되었고 [tests/test_loading_time_contract.py:317](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/tests/test_loading_time_contract.py:317) 이후 fake SQL·checkpoint contract test가 통과한다. 실제 source 응답과 MySQL에서 중간 batch 실패 후 재실행하는 smoke test는 실행하지 않았으므로 운영 복구 완료로 확대하지 않는다.

---

## LOAD-005. sink 직접 호출 입력 검증

### 우선순위

**P2 — 수정 반영 완료. 필드별 전체 검증의 실제 DB 경로는 별도 smoke test**

### 관련 계약 및 구현

현재 loading README는 FAQ document와 등록현황 row에 `content_hash`를 포함한 준비 계약을 입력으로 기술한다.

- [src/loading/README.md:55](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/README.md:55)
- [src/loading/README.md:57](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/README.md:57)

FAQ sink는 prepared document의 필수 text, 절대 HTTP(S) URL, source timestamp, `is_active` boolean을 검증한다.

- [src/loading/faq.py:33](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/faq.py:33): FAQ 입력 계약 검증
- [src/loading/faq.py:104](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/faq.py:104): JSONL 저장 전 검증
- [src/loading/faq.py:163](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/faq.py:163): Mongo 저장 전 검증

등록현황 sink는 다섯 business key, `source_name`, `source_url`, `run_id`, `collected_at`, non-empty `content_hash`, non-negative integer 또는 null인 `quantity`를 검증한다.

- [src/loading/registration.py:232](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/registration.py:232): 공통 등록현황 입력 계약 검증
- [src/loading/registration.py:309](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/registration.py:309): JSONL 저장 전 검증
- [src/loading/registration.py:374](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/registration.py:374): SQL 저장 전 검증

### 확인 결과

현재 contract test에서 다음 malformed input이 거부된다.

    FAQ: question 등 필수 prepared field가 없는 document
    Registration: 음수 quantity가 있는 row

### 영향

- loading sink를 직접 호출해도 prepared contract 누락이 JSONL·Mongo·SQL 저장 전에 검출된다.
- `quantity`의 음수·boolean·비정수 값과 필수 metadata 누락을 차단한다.
- loading README의 입력 계약과 sink의 실제 검증 범위가 일치한다.

### 현재 판정 및 잔여 확인

loading이 최소 prepared contract를 독립적으로 검증하는 방식으로 구현·문서화했고 회귀 테스트가 통과했다. 현재 테스트는 대표적인 누락 필드와 음수 quantity를 확인하므로 실제 DB에 잘못된 record가 저장되지 않는지의 smoke test는 별도 조건으로 남지만, 기존의 “직접 호출 입력 검증 부족” 이슈는 해소되었다.

---

## LOAD-006. loading 단위 테스트 증거와 Git 추적 상태

### 우선순위

**P1 — 수정 반영 완료. 현재 HEAD 기준 모듈 단위 테스트·파일 추적 완료**

### 확인 결과

현재 Conda `sandbox`에서 다음 결과를 확인했다.

    python -m pytest -q tests/test_loading_time_contract.py
    14 passed in 0.14s

    python -m pytest -q
    80 passed in 0.26s

현재 [tests/test_loading_time_contract.py](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/tests/test_loading_time_contract.py)는 `git ls-files`에 포함되어 있고, loading source·README·requirements·migration도 현재 HEAD `7a88f55`에 추적되어 있다.

해당 테스트는 [tests/test_loading_time_contract.py:9](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/tests/test_loading_time_contract.py:9)의 Mongo migration과 [tests/test_loading_time_contract.py:10](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/tests/test_loading_time_contract.py:10)의 SQL migration을 import한다. 두 migration이 현재 HEAD에 추적되어 있으므로 현재 HEAD 기준 clean checkout의 import 조건도 충족한다. 다만 원격 `origin/fix/validate-pipeline` ref가 `7a88f55`를 가리키는지는 별도 확인 대상이다.

### 현재 테스트의 공백

현재 loading 전용 테스트는 JSONL timestamp, JSON quota 날짜, SQL 값 변환, SQL unchanged write 생략, SQL checkpoint, transaction rollback, FAQ·등록현황 입력 검증, Mongo validator 상수, incremental 계약, migration SQL splitter를 확인한다.

다음은 여전히 실제 외부 시스템 검증 범위가 아니다.

- 실제 MySQL Upsert·rollback·동일 batch 재실행
- 실제 MongoDB validator·index·Upsert
- 실제 migration 적용 및 clean checkout dependency 설치
- quota exhaustion 및 다중 process 경합

참고 폴더의 테스트 결과는 현재 대상 저장소의 commit 단위 증거가 아니므로 현재 loading 모듈의 완료 결과로 사용할 수 없다.

### 영향

- 현재 HEAD 기준 module unit-test 완료 증거와 test·migration 파일 추적은 확보되었다.
- 실제 DB smoke test를 수행하지 않았으므로 운영 DB의 schema·write 성공까지 보장하지 않는다.
- 원격 branch에서 동일 commit이 보이는지는 local `origin` ref와 push 상태를 별도로 확인해야 한다.

### 현재 판정 및 잔여 확인

사용자가 반영한 `0817a7f`와 `7a88f55` commit으로 loading source·전용 test·migration의 Git 추적을 확인했고, 현재 HEAD에서 loading 전용 14개와 전체 80개 테스트가 통과했다. 따라서 코드·단위 테스트·현재 HEAD 파일 추적 기준의 완료 기준은 충족했다. 실제 DB smoke test와 원격 branch 반영 여부는 별도 확인 조건이다.

---

## LOAD-007. JSON quota·state·checkpoint 파일의 다중 프로세스 경합 보호 없음

### 우선순위

**P2-조건부 — 보류 유지. 단일 worker 전제 또는 경합 보호 정책 결정 필요**

### 관련 구현

JSON quota ledger는 현재 값을 읽고, 증가시키고, atomic replace로 저장하는 순서다.

- [src/loading/registration.py:116](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/registration.py:116)
- [src/loading/registration.py:126](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/registration.py:126)

checkpoint와 registration state도 파일 단위 atomic write는 사용하지만 lock, compare-and-swap, process ownership 검증은 확인되지 않는다.

- [src/loading/usedcar.py:67](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/usedcar.py:67)
- [src/loading/registration.py:54](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/registration.py:54)

### 영향

- 두 worker가 같은 quota state를 읽으면 quota 초과 예약 또는 증가분 유실이 발생할 수 있다.
- 두 pipeline이 같은 checkpoint를 저장하면 더 늦게 완료된 실행이 이전 성공 위치를 덮어쓸 수 있다.
- atomic replace는 부분 파일 방지는 제공하지만 read-modify-write 전체의 경합 방지는 제공하지 않는다.

### 확정 요청 및 승인 기준

1. JSON sink·quota·checkpoint를 단일 process 전용으로 제한할지, 다중 worker를 지원할지 결정한다.
2. 다중 worker를 지원한다면 lock 또는 DB 기반 atomic state 저장을 사용한다.
3. 단일 worker 전제라면 pipeline lock과 중복 실행 방지 조건을 상위 운영 계약에 명시한다.
4. quota 초과, checkpoint overwrite, 동시 실행 중단 후 재시작을 테스트한다.

### 수정 요청 범위

loading 내부 state 저장 방식과 pipeline 실행 lock의 연계가 직접 범위다. 실제 process orchestration의 오류는 이번 보고서에서 언급만 하고 별도 수정 대상으로 산정하지 않는다.

## 3. 범위 외 발견 사항

다음 항목은 loading과 연관되지만 요청 대상인 `src/loading` 외부의 파일 또는 문서 문제이므로 이번 보고서에서는 언급만 하고 수정 범위에서 제외한다.

- [src/pipelines/usedcar.py](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/usedcar.py)는 LOAD-004 계약 확인을 위해 함께 반영된 연관 파일이며, loading 이슈의 직접 범위와 구분한다.
- [src/collection/usedcar.py](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/collection/usedcar.py)는 source sequence·page metadata의 외부 계약 확인 대상이다.
- [docs/Data_Specification.md:16](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/docs/Data_Specification.md:16)는 중고차 테이블을 4개로 기술하지만 현재 loading 구현은 5개 참조 테이블과 `vehicle_listings`를 사용한다.
- [docs/Cost_Estimation.md:29](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/docs/Cost_Estimation.md:29)는 FAQ와 중고차 매물을 MongoDB에 저장한다고 기술하지만 현재 loading 구현과 reference loading README는 FAQ는 MongoDB, 중고차는 SQL로 구분한다.
- 문서 index와 migration의 Git 추적 상태는 repository organization 및 clean checkout 문제로, 본문 LOAD-003·LOAD-006에서만 현재 판정을 기록한다.

## 4. 현재 잔여 확인 순서

1. LOAD-002·LOAD-003·LOAD-004: 실제 MongoDB/MySQL 및 source를 사용한 migration·Upsert·checkpoint smoke test
2. LOAD-003·LOAD-006: 원격 branch가 `7a88f55`를 포함하는지 push/fetch 상태 확인
3. LOAD-007: 다중 worker 지원 여부와 lock/CAS/DB state 정책 결정

현재 HEAD와 단위 테스트 기준으로 LOAD-001·LOAD-002·LOAD-003·LOAD-004·LOAD-005·LOAD-006은 반영되었다. 실제 DB smoke test와 원격 branch 반영 여부는 아직 확인하지 않았고, LOAD-007은 지시대로 보류 상태를 유지한다.

## 5. 결정사항

본 보고서에는 결정사항을 기입하지 않는다. 이 영역은 지시자가 직접 작성한다.
