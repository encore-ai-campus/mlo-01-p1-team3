# Pipelines 구현 모듈 이슈 보고서

- 작성일: 2026-08-13
- 대상 저장소: `/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3`
- 대상 모듈: `src/pipelines`
- 참고 폴더: `/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/ref/mlo-01-p1-team3-a`
- 목적: 현재 pipeline 구현의 내부 계약·외부 계약·문서 정합성·실행 안정성을 확인하고, 정상 동작 승인 전 해소하거나 결정해야 하는 이슈를 보고
- 보고서 상태: 아래 3절 이후는 수정 전 전수조사 근거이며, 2.1절과 5절에 현재 구현·검증 결과를 반영함
- 조치 범위: 구동에 필요한 P0~P2 항목에 한해 `src/main.py`, `src/pipelines`, 관련 runtime 설정·collector 계약, pipeline 단위 테스트와 문서를 보완함. 실제 SQL/Mongo/live 적재는 수행하지 않음

## 0. 최신 구현 반영 상태

2026-08-13 후속 구현 기준 상태는 다음과 같다. SQL 운영 observability와 Reject-only checkpoint 정책은 구동 경로를 넘어서는 조건부 항목으로 유지한다.

| ID | 결정 및 현재 상태 |
|---|---|
| PIPE-001 | 해결 — `run_once()` 중심 pipeline 테스트 4건 추가, 전체 84건 통과 |
| PIPE-002 | 해결 — 정상 Validate 이벤트와 stage/logic별 실패 로그 반영 |
| PIPE-003 | 유지 — local JSONL과 DB application log의 source of truth 결정은 범위 제외 |
| PIPE-004 | 해결 — Registration dry-run quota/state 영속화 제거 |
| PIPE-005 | 해결 — Used-car page 간 `dataset_epoch` 변경 fail-closed 및 이전 성공 checkpoint 보존 |
| PIPE-006 | 유지 — SQL `pipeline_runs` count·실패 이력 확장은 loading/observability 범위 |
| PIPE-007 | 해결 — 세 pipeline 공통 반환 필드와 FAQ `checkpoint_path: null` 반영 |
| PIPE-008 | 해결 — quota 소진을 `registration_quota_exhausted` 실패로 반환 |
| PIPE-009 | 해결 — Used-car dry-run event와 batch/누적 count 단위 분리 |
| PIPE-010 | 해결 — SQL canonical checkpoint 조회 후 local JSON fallback 순서 반영 |
| PIPE-011 | 조건부 미결 — Reject-only page의 checkpoint 진행 정책은 business 결정 필요 |
| PIPE-012 | 해결 — 직접 `run_once()` 호출에서도 sink 입력을 선검증 |

## 1. 판정 기준

| 우선순위 | 의미 |
|---|---|
| P0 | pipeline 모듈의 재현 가능한 단위 테스트 또는 실행 근거가 없어 정상 실행을 승인할 수 없는 차단 이슈 |
| P1 | 정상 fixture 경로는 실행될 수 있으나 내부·외부 계약 또는 운영 안전성을 위해 반드시 해소해야 하는 이슈 |
| P1-조건부 | 실제 DB·상위 호출자·source 계약을 확인한 뒤 승격 여부를 결정할 이슈 |
| P2 | 정상 경로를 즉시 차단하지 않지만 결과 의미·방어력·문서 정합성을 저해하는 이슈 |

## 2. 요약

현재 `src/main.py`가 공통 진입점이며, 각 `src/pipelines/*.py`가 해당 source의 비즈니스 계약과 `run_once()` 실행 단위를 소유한다. FAQ·자동차등록현황·중고차의 fixture 경로에서 Collect → Preprocess → Validate → Load를 실행하고 공통 top-level `run_id`를 전달한다.

P0~P2 중 구동에 직접 필요한 항목은 반영했으며, 모듈 단위 테스트와 정적 검사가 통과했다. 실제 SQL/Mongo/live 연결은 이번 구현 검증 범위에 포함하지 않았으므로 해당 경로를 정상으로 보고하지 않는다.

| ID | 우선순위 | 모듈 | 이슈 | 현재 판정 |
|---|---|---|---|---|
| PIPE-001 | P0 | pipeline 테스트·fixture | `run_once()` 단위 테스트와 현재 checkout의 재현 fixture 부재 | 해결 |
| PIPE-002 | P1 | 세 pipeline·로그 | 정상 실행 Validate 이벤트 누락 및 실패 단계 정보 불일치 | 해결 |
| PIPE-003 | P1-조건부 | JsonlLogger·application logs | 참조 문서의 DB 운영 로그 계약과 현재 local JSONL 구현의 경계가 확정되지 않음 | 범위 제외·결정 필요 |
| PIPE-004 | P1 | Registration | dry-run에서도 quota/API 호출 상태 변경 | 해결 |
| PIPE-005 | P1 | Used-car | 한 실행 안에서 dataset epoch 변경을 감지하지 못할 수 있음 | 해결 |
| PIPE-006 | P1 | SQL 연계 | `pipeline_runs`에 pipeline별 수집·전처리·검증 count 및 실패 이력이 충분히 기록되지 않음 | 범위 제외 |
| PIPE-007 | P1 | README·세 pipeline 결과 | 공통 반환 계약의 필드가 FAQ·Registration 구현과 불일치 | 해결 |
| PIPE-008 | P2 | Registration | quota 소진을 `OK`·0건 성공으로 반환 | 해결 |
| PIPE-009 | P2 | Used-car | dry-run `batch_committed`와 누적 count가 실제 batch 동작을 오표현 | 해결 |
| PIPE-010 | P2 | Used-car checkpoint | 손상된 local checkpoint가 SQL canonical checkpoint보다 먼저 실패를 발생시킴 | 해결 |
| PIPE-011 | P1-조건부 | Used-car Reject·checkpoint | 모든 source row가 Reject되어도 checkpoint가 전진할 수 있음 | 정책 결정 필요 |
| PIPE-012 | P2 | 직접 `run_once()` 호출 | dry-run에서는 unsupported sink 검증이 생략됨 | 해결 |

### 확인된 정상 경로

- 공통 진입점: `python -m src.main --pipeline all --profile fixture ... --period 2026-06`
- FAQ fixture 2건: 1 page, 2 valid, 2 insert
- Registration fixture: 1회 API 논리 호출, 2 raw record에서 40 normalized row 생성, 40 insert
- Used-car fixture: initial 2 batch, 3 record, 3 insert, checkpoint `after_seq=2`
- 정상 run에서 세 pipeline 모두 `validation_completed` event 기록
- `python -m pytest -q`: `84 passed in 0.31s` (Conda `sandbox`)
- `python -m compileall -q src`, `python -m ruff check src/main.py src/pipelines src/common/config.py src/collection/faq.py`, `git diff --check` 통과

위 실행은 JSONL 및 fixture 경로에 대한 결과이다. 실제 MongoDB·MySQL 연결, migration 적용, DB write/Upsert는 이번 점검에서 수행하지 않았으므로 해당 경로를 정상으로 보고하지 않는다.

## 2.1 구현 후 검증 및 잔여 범위

### 반영한 구동 계약

- `src/main.py`를 `faq|registration|usedcar|all` 선택이 가능한 공통 진입점으로 추가했다. fixture profile은 안전한 기본값이며 live profile은 명시적으로 선택한다.
- FAQ pipeline에 allowlist, 요청 간격 1초 이상, 최대 2 page, page당 최대 10문항 계약을 반영하고 source URL·license·attribution·content hash 보존 경계를 문서화했다.
- Registration pipeline에 `form_id=5498`, `style_num=2`, `start_dt=end_dt=YYYYMM`, 논리적 1회 요청, quota 소진 실패, dry-run quota 비영속화를 반영했다.
- Used-car pipeline에 초기 cursor·증분 `after_seq`, 1초/500건 상한, `dataset_epoch` 일관성, 성공 적재 후 checkpoint, SQL 우선·local fallback 경계를 반영했다.
- 세 pipeline의 공통 결과 필드(`status`, `run_id`, `mode`, count, `dry_run`, `checkpoint_path`)와 정상 Validate event를 보완했다.

### 범위에서 유지한 항목

- `PIPE-003`: local JSONL을 보조 운영 로그로 볼지 DB `application_logs`를 필수 source of truth로 볼지 결정하지 않았으며, 실제 DB 로그 검증을 수행하지 않았다.
- `PIPE-006`: SQL `pipeline_runs`에 세 pipeline의 stage count와 실패 이력을 모두 기록하는 확장은 `src/loading`·migration·observability 작업으로 분리했다.
- `PIPE-011`: Reject-only batch에서 checkpoint를 진행할지, 실패·재처리 상태로 남길지 business 정책이 필요하다. 현재 정상 fixture 실행에는 영향이 없다.
- 실제 live API 호출, MongoDB/MySQL 연결, migration 적용, 외부 Upsert는 수행하지 않았다.

## 3. 레퍼런스 및 현재 checkout 비교

> 이 절과 이후 개별 PIPE 항목은 2026-08-13 구현 전 전수조사에서 확보한 원인·영향·승인 기준을 보존한 것이다. 현재 판정은 0절, 2절, 2.1절과 아래 최종 판정을 우선한다.

- 현재 `faq.py`, `registration.py`, `__init__.py`는 local reference의 대응 파일과 동일하다.
- 현재 `usedcar.py`는 local reference와 다르며, SQL progress key, batch별 SQL run ID, incremental contract fail-closed 처리가 추가된 현재 구현이다.
- 현재 [pipelines README:33](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/README.md:33)은 reference README보다 SQL checkpoint와 `incremental_contract_missing` 계약을 확장하여 설명한다.
- 초기 점검 시 대상 `src/pipelines` 파일은 미커밋 상태였고 pipeline 전용 테스트와 fixture가 없었다. 후속 구현에서 `src/main.py`, 세 pipeline, 관련 runtime 계약과 `tests/test_pipelines.py`를 추가·보완했다.

## PIPE-001. pipeline `run_once()` 단위 테스트와 재현 fixture가 없음

### 우선순위

**P0 — 요청된 완료 기준인 모듈 단위 테스트 결과가 완결되지 않음**

### 확인 내용

현재 전체 테스트는 80개 통과했지만, pipeline의 `run_once()`를 직접 호출하는 테스트는 확인되지 않았다. [test_loading_time_contract.py:23](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/tests/test_loading_time_contract.py:23)에서 `pipelines.usedcar._require_incremental_contract` helper만 import하여 검증한다.

현재 `tests/`에는 `tests/fixtures`가 없으며, 이번 정상 경로 실행은 현재 checkout 외부의 reference fixture를 사용했다. 따라서 새 checkout에서 FAQ·Registration·Used-car pipeline 정상 경로를 같은 입력으로 재현할 수 없다.

### 영향

- 전체 `pytest` green 결과가 pipeline orchestration 정상 동작을 보장하지 않는다.
- sink별(JSON·Mongo·SQL), `dry_run`, Reject, quota 소진, checkpoint 실패, API 오류 경로의 회귀를 검증할 수 없다.
- reference fixture가 현재 구현의 테스트 자산인지, 단순 참고 데이터인지 경계가 불명확하다.
- 사용자가 지정한 “해당 모듈 단위 테스트 결과가 온전히 나왔을 경우” 완료 기준을 충족하지 못한다.

### 승인 기준

1. 세 pipeline 각각에 대해 `run_once()` 정상·실패·재실행·dry-run 테스트를 현재 checkout에서 실행한다.
2. FAQ Reject, Registration quota 소진/API 오류, Used-car incremental contract·dataset epoch·checkpoint 실패 fixture를 포함한다.
3. JSONL sink 결과와 stage log event, 반환 mapping, checkpoint 상태를 함께 검증한다.
4. SQL/Mongo는 실제 연결 검증 또는 명시적인 contract/mock 경계를 별도로 기록한다.
5. `python -m pytest -q` 결과에서 pipeline 전용 테스트 수와 결과를 확인한다.

### 수정 범위 산정

- `tests/`의 pipeline 전용 테스트·fixture
- 필요 시 `src/pipelines`의 계약 구현

이번 보고서 작성에서는 수정하지 않는다.

## PIPE-002. 정상 실행 Validate 이벤트 누락 및 실패 단계 정보 불일치

### 우선순위

**P1 — 정상 실행 관측성 계약 미충족**

### 관련 계약 및 구현

[pipelines README:33](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/README.md:33)은 모든 run이 `Collect → Preprocess → Validate → Load` 순서로 로그를 남긴다고 정의한다.

그러나 Validate 로그는 Reject가 있을 때만 실행된다.

- FAQ: [faq.py:94](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/faq.py:94)
- Registration: [registration.py:170](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/registration.py:170)
- Used-car: [usedcar.py:149](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/usedcar.py:149)

정상 fixture 실행 로그에는 `Collect`, `Preprocess`, `Load` 이벤트만 있고 `Validate` 이벤트가 없었다.

실패 시 stage 정보도 일관되지 않는다.

- Registration의 모든 예외는 [registration.py:225](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/registration.py:225)에서 `vehicle_registration.collect`로 기록된다. Load 또는 Preprocess 실패도 Collect 실패로 보인다.
- Used-car의 [usedcar.py:217](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/usedcar.py:217)는 `stage_name`, `logic_name` 없이 일반 `run_failed`만 기록한다.
- FAQ의 transform 예외는 Collect/Load try 블록 밖에서 발생할 수 있어 stage-specific `run_failed` 이벤트가 보장되지 않는다.

### 영향

- 운영자가 정상 run의 validation 수행 여부와 검증 건수를 로그만으로 확인할 수 없다.
- 오류가 발생한 실제 stage와 재실행 필요 지점을 판별하기 어렵다.
- [Requirements Traceability AC-OBS-001:217](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/docs/Requirements_Traceability.md:217)의 run/stage별 status·count unit·sanitized error 증거를 충족한다고 볼 수 없다.

### 승인 기준

1. Reject가 0건이어도 Validate 완료 이벤트를 남긴다.
2. Validate 이벤트에 입력 count, valid count, rejected count, reject rule 결과를 기록한다.
3. Collect·Preprocess·Validate·Load 각각의 실패를 해당 stage와 logic name으로 기록한다.
4. 모든 실패가 sanitized `error_code`와 함께 `run_failed` 또는 stage-specific failure event로 남는지 fixture로 검증한다.

### 수정 범위 산정

- `src/pipelines/faq.py`
- `src/pipelines/registration.py`
- `src/pipelines/usedcar.py`
- pipeline log 테스트

## PIPE-003. DB 운영 로그 계약과 local JSONL 로그 구현의 경계가 확정되지 않음

### 우선순위

**P1-조건부 — 참조 Data Specification을 운영 계약으로 채택하는 경우**

### 관련 계약 및 구현

현재 pipeline은 [common/logging_utils.py:55](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/common/logging_utils.py:55)의 `JsonlLogger`를 사용하고, [logging_utils.py:74](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/common/logging_utils.py:74)에서 local JSONL 파일에 기록한 뒤 stderr로 mirror한다.

참조 Data Specification은 `application_logs.application_logs`에 pipeline·stage·logic·event·error를 기록하도록 정의하고, [참조 Data Specification:322](</Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/ref/mlo-01-p1-team3-a/docs/05_Data Specification.md:322>)부터 세 pipeline의 logic name을 열거한다.

현재 checkout의 `src/pipelines` 실행만으로 해당 DB application log가 기록된다는 증거는 없다. 별도 운영 observability 계층이 이를 담당하는지, pipeline의 외부 계약이 local JSONL까지만인지 결정되어 있지 않다.

### 영향

- DB에서 run/stage별 운영 이력을 조회해야 하는 요구라면 현재 pipeline 실행 결과만으로는 충족 여부를 확인할 수 없다.
- local JSONL과 DB 로그의 source of truth가 불명확하다.
- 실제 DB를 실행하지 않았으므로 연결·적재·secondary log sink failure의 안정성도 미검증이다.

### 승인 기준

1. application log 저장소의 책임 주체와 source of truth를 결정한다.
2. local JSONL만 허용하는 경우 해당 경계를 pipeline README와 운영 문서에 명시한다.
3. DB 로그가 필수인 경우 세 pipeline의 logic name, sanitized error, stage count가 실제 DB에 기록되는지 검증한다.
4. 보조 로그 저장 실패가 pipeline load 결과를 오염시키지 않는지 별도 검증한다.

### 수정 범위 산정

pipeline 외부의 logging/observability 및 migration 경로가 포함될 수 있다. 이번 요청의 `src/pipelines` 범위에서는 수정하지 않는다.

## PIPE-004. Registration dry-run이 quota/API 상태를 변경함

### 우선순위

**P1 — dry-run 의미와 실제 부작용 불일치**

### 관련 구현

Registration은 [registration.py:71](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/registration.py:71)에서 quota ledger를 만들고, [registration.py:107](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/registration.py:107)에서 `dry_run` 여부와 관계없이 source fetch 및 `quota.reserve`를 실행한다. sink 저장은 생략하지만 quota ledger의 reservation은 별도 side effect이다.

이번 검증에서 fresh output directory로 `--dry-run`을 실행했을 때 결과는 `status=OK`, `api_calls=1`, `dry_run=true`였고, sink JSONL은 생성되지 않았지만 registration state의 `used_count`와 `last_call_at`은 변경되었다.

### 영향

- 운영자가 dry-run을 사전 검증으로 사용해도 당일 API quota를 소비한다.
- 실제 운영 API를 fixture 없이 호출하는 경우 외부 API 호출 자체가 발생한다.
- dry-run 후 실제 run이 quota 소진으로 차단될 수 있다.

### 승인 기준

1. dry-run에서 source/API 호출과 quota reservation을 허용하는지 결정한다.
2. 허용한다면 “load만 생략하는 실행”으로 명시하고 quota side effect를 반환 결과와 문서에 표시한다.
3. 허용하지 않는다면 source fetch·quota state·sink·checkpoint가 모두 변경되지 않는지 검증한다.
4. JSON quota와 SQL quota에서 동일한 dry-run 의미를 확인한다.

### 수정 범위 산정

- `src/pipelines/registration.py`
- quota ledger 및 dry-run 테스트

## PIPE-005. Used-car dataset epoch 검사가 페이지 간 변경을 놓칠 수 있음

### 우선순위

**P1 — source snapshot 일관성 미보장**

### 관련 구현

Used-car는 [usedcar.py:84](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/usedcar.py:84)에서 `checkpoint`의 dataset epoch와 현재 page epoch를 비교한다. 그러나 page 처리 후 갱신되는 값은 `last_checkpoint`이고, 다음 page의 비교 기준으로 사용하는 `checkpoint`는 갱신되지 않는다.

두 page가 순서대로 epoch A와 epoch B를 반환하는 fake source를 실행했을 때 `dataset_epoch_changed` 오류 없이 완료되었고 최종 checkpoint에는 B가 저장되었다. 즉, 한 run 안에서 서로 다른 snapshot의 page가 섞일 수 있다.

### 영향

- initial cursor sync가 source snapshot 경계를 보장하지 못할 수 있다.
- page 간 insert/update가 발생하는 source에서 일부 누락·중복·순서 역전이 발생할 수 있다.
- checkpoint에는 마지막 epoch만 남아 이전 page의 snapshot 경계가 사라진다.

### 승인 기준

1. dataset epoch가 run 전체에서 불변인지 source 계약을 확인한다.
2. 불변이어야 한다면 첫 page epoch를 기준으로 모든 후속 page를 비교한다.
3. 변경을 감지하면 해당 run의 load/checkpoint 처리 정책과 반환 error code를 확정한다.
4. epoch A → A 정상, epoch A → B 실패, epoch 없음 정책을 각각 테스트한다.

### 수정 범위 산정

- `src/pipelines/usedcar.py`
- used-car collection/pipeline contract test

## PIPE-006. SQL `pipeline_runs` 실행 이력이 pipeline 계약을 충분히 반영하지 않음

### 우선순위

**P1 — SQL 운영 이력 및 checkpoint 감사 정보 미완결**

### 관련 계약 및 구현

참조 Data Specification의 `pipeline_runs`는 collected/preprocessed/valid/rejected/inserted/updated/unchanged/api_calls, progress key, error 정보를 저장하도록 정의한다.

- [참조 Data Specification:234](</Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/ref/mlo-01-p1-team3-a/docs/05_Data Specification.md:234>)
- 현재 schema: [V001__mvp_schema.sql:168](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/migrations/sql/V001__mvp_schema.sql:168)

현재 Used-car pipeline은 SQL sink에 [usedcar.py:159](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/usedcar.py:159)부터 records, checkpoint, batch run ID, started_at을 전달한다. SQL loader의 `_record_pipeline_success()`는 [loading/usedcar.py:446](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/usedcar.py:446)부터 inserted/updated/unchanged와 progress key만 INSERT한다. schema에 있는 collected/preprocessed/valid/rejected/api_calls는 pipeline 실행 결과로 전달되지 않아 기본값에 머문다.

또한 현재 확인된 SQL pipeline run 기록 경로는 Used-car SQL sink의 성공 batch 기록이며, FAQ·Registration pipeline의 SQL `pipeline_runs`와 실패 run 기록은 확인되지 않았다.

### 영향

- SQL에서 run별 수집량·전처리량·Reject량·API 호출량을 감사할 수 없다.
- SQL checkpoint가 어느 top-level pipeline run의 어떤 stage 결과인지 추적하기 어렵다. 현재 문서상 top-level run ID와 batch run ID가 분리되지만 schema에는 상관관계 필드가 없다.
- 실패 run의 sanitized error와 상태가 `pipeline_runs`에 남는다는 보장이 없다.
- SQL checkpoint를 실제 운영 source of truth로 사용할 때 observability와 checkpoint 감사가 분리된다.

이번 항목은 실제 SQL을 실행한 결과가 아니라 현재 pipeline·loading·schema 정적 대조 결과이다.

### 승인 기준

1. `pipeline_runs`의 기록 단위를 top-level run, batch run 중 무엇으로 할지 확정한다.
2. 세 pipeline별 stage count·load count·api_calls·error code를 SQL 이력에 반영할지 결정한다.
3. 성공·실패·0건 성공의 상태와 progress key 사용 규칙을 검증한다.
4. 실패 run의 progress key가 다음 incremental checkpoint로 선택되지 않는지 실제 SQL 또는 contract test로 확인한다.

### 수정 범위 산정

- `src/pipelines` 및 `src/loading` SQL 연계
- `migrations/sql` schema/계약 테스트

이번 보고서 작성에서는 외부 파일을 수정하지 않는다.

## PIPE-007. 공통 반환 mapping 계약과 pipeline별 구현 결과가 불일치함

### 우선순위

**P1 — 외부 호출자와 CLI가 결과 필드를 일관되게 해석할 수 없음**

### 관련 계약 및 구현

[pipelines README:54](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/README.md:54)는 모든 `run_once()` 결과에 `status`, `run_id`, `mode`, 각 count, checkpoint 경로가 있다고 정의한다.

현재 구현은 pipeline별로 반환 shape가 다르다.

- FAQ의 결과는 [faq.py:116](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/faq.py:116)부터 `pages`와 count를 반환하지만 `mode`, `checkpoint_path`가 없다.
- Registration의 결과는 [registration.py:199](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/registration.py:199)부터 `period`, `periods`, quota 필드를 반환하지만 `mode`, `checkpoint_path`가 없다.
- Used-car만 [usedcar.py:201](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/usedcar.py:201)부터 `mode`와 `checkpoint_path`를 반환한다.
- FAQ CLI는 [faq.py:155](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/faq.py:155)에서 `faq_state_path`를 설정하지만 `run_once()`는 해당 checkpoint를 사용하지 않는다.

### 영향

- scheduler·dashboard·공통 wrapper가 pipeline별 예외 필드를 별도 처리해야 한다.
- FAQ의 `checkpoint_path`는 문서상 존재하지만 실제 checkpoint가 없으므로 운영자가 상태 경로를 오인할 수 있다.
- 문서 기반 contract test를 작성할 때 어떤 필드가 필수인지 결정할 수 없다.

### 승인 기준

1. 공통 필수 필드와 pipeline별 확장 필드를 분리해 정의한다.
2. checkpoint가 없는 pipeline은 결과·README에서 checkpoint 필드를 제거하거나 `null` 정책을 명시한다.
3. 세 pipeline 반환 mapping에 대한 schema/contract test를 추가한다.
4. CLI JSON과 `run_once()` 직접 호출 결과의 필드 의미를 일치시킨다.

### 수정 범위 산정

- `src/pipelines/README.md`
- 세 pipeline의 결과 mapping 및 contract test

## PIPE-008. Registration quota 소진이 `OK`·0건 성공으로 반환됨

### 우선순위

**P2 — 운영 상태 오판 가능**

### 관련 구현 및 확인 결과

Registration은 [registration.py:106](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/registration.py:106)에서 `quota.remaining > 0`일 때만 fetch한다. quota가 0이면 source 호출 없이 [registration.py:199](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/registration.py:199)부터 `status=OK`, `periods=0`, `collected_count=0`, `api_calls=0`을 반환하고 [registration.py:216](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/registration.py:216)에서 `run_succeeded`를 기록한다.

일일 quota를 1로 제한한 뒤 같은 state로 두 번째 실행했을 때 이 동작이 재현되었다.

### 영향

- 스케줄러가 quota block을 정상 처리로 오인한다.
- 당일 처리되지 않은 period가 있는데도 성공 run으로 집계된다.
- 재시도·알림·운영 대시보드가 quota 소진을 구분하지 못한다.

### 승인 기준

1. quota 소진을 `BLOCKED`, `SKIPPED`, `FAILED` 중 어떤 상태로 표현할지 결정한다.
2. 결과 mapping과 log에 `quota_exhausted` 또는 동등한 sanitized code를 남긴다.
3. period 미처리와 정상적인 0건 API 응답을 구분한다.
4. quota 소진 후 checkpoint/state를 성공 처리하지 않는지 확인한다.

### 수정 범위 산정

- `src/pipelines/registration.py`
- quota 상태·scheduler contract test

## PIPE-009. Used-car dry-run과 batch 로그의 count·event 의미가 실제 동작과 다름

### 우선순위

**P2 — 관측성 및 count unit 불일치**

### 관련 구현 및 확인 결과

Used-car는 sink가 없는 dry-run에서도 [usedcar.py:180](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/usedcar.py:180)부터 `batch_committed`, “batch load and checkpoint completed”를 기록한다. 그러나 dry-run에서는 sink와 checkpoint가 실제로 저장되지 않고, event의 inserted/updated/unchanged count는 0으로 기록된다.

정상 실행에서도 [usedcar.py:187](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/usedcar.py:187)의 count는 현재 batch가 아니라 run 누적값이다. initial 2번째 batch가 1건이어도 `batch_committed.inserted_count=3`으로 기록되는 결과를 확인했다.

### 영향

- dry-run 로그만 보면 실제 load/checkpoint가 완료된 것으로 오인할 수 있다.
- `batch_committed`를 batch 단위 이벤트로 집계하면 count가 중복 합산된다.
- AC-OBS의 count unit을 운영자가 일관되게 해석할 수 없다.

### 승인 기준

1. dry-run event를 `load_skipped` 등 별도 event로 표현할지 결정한다.
2. batch event에는 batch count, run final event에는 누적 count를 기록하도록 단위를 분리한다.
3. dry-run에서 checkpoint·sink·quota side effect가 없는지 pipeline별로 검증한다.
4. 로그 검증 fixture에서 batch 합계와 최종 결과 count가 일치하는지 확인한다.

### 수정 범위 산정

- `src/pipelines/usedcar.py`
- logging/count contract test

## PIPE-010. 손상된 local checkpoint가 SQL canonical checkpoint보다 먼저 실패함

### 우선순위

**P2 — fallback 복구 경로 취약**

### 관련 계약 및 구현

README는 SQL sink의 `pipeline_runs.progress_key`를 우선 사용하고 local JSON을 fallback으로 설명한다.

- [pipelines README:35](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/README.md:35)
- [loading README:121](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/README.md:121)

그러나 Used-car는 [usedcar.py:47](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/usedcar.py:47)에서 local checkpoint를 먼저 읽는다. `CheckpointStore.load()`는 [loading/usedcar.py:97](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/loading/usedcar.py:97)에서 JSON이 손상되면 예외를 발생시킨다. 이 예외는 SQL sink를 만들고 SQL checkpoint를 조회하기 전 발생한다.

### 영향

- local JSON이 손상되어도 유효한 SQL checkpoint로 복구할 수 없다.
- local 파일은 fallback이어야 하지만 실제 실행 순서상 SQL canonical 경로를 차단한다.
- 장애 복구 시 checkpoint를 수동 삭제해야 할 수 있다.

### 승인 기준

1. local checkpoint 손상, 부재, 유효 상태와 SQL checkpoint 유효 상태를 조합해 우선순위를 테스트한다.
2. SQL canonical checkpoint가 있으면 local 손상을 무시할지, 명시적 오류로 중단할지 결정한다.
3. fallback 선택 결과와 사용된 checkpoint source를 로그·결과에 남긴다.

### 수정 범위 산정

- `src/pipelines/usedcar.py`
- `src/loading/usedcar.py` checkpoint contract test

## PIPE-011. 모든 source row가 Reject되어도 Used-car checkpoint가 전진할 수 있음

### 우선순위

**P1-조건부 — Reject를 non-blocking으로 인정하는지 결정 필요**

### 관련 구현

Used-car는 page state로 `next_checkpoint`를 만든 뒤 [usedcar.py:123](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/usedcar.py:123)부터 transform한다. valid row가 0건이고 rejected row만 있어도 [usedcar.py:159](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/usedcar.py:159)부터 sink가 호출되고, [usedcar.py:178](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/usedcar.py:178)에서 checkpoint가 저장될 수 있다.

현재 문서는 “적재 성공 전 checkpoint를 전진시키지 않는다”고 정의하지만, Reject-only page를 성공적인 Load로 볼지에 대한 정책은 명시하지 않는다.

### 영향

- Reject된 source row가 재실행되지 않고 source cursor가 지나갈 수 있다.
- Reject 원본 또는 상세 사유가 별도 저장되지 않으면 데이터가 조용히 유실될 수 있다.
- Reject가 일시적 변환 오류인지 영구적인 schema 오류인지 구분하지 못한다.

### 승인 기준

1. Reject-only batch를 `SUCCESS`, `PARTIAL`, `FAILED` 중 무엇으로 처리할지 결정한다.
2. checkpoint를 전진시키는 경우 Reject row와 error code를 재처리 가능한 형태로 보존한다.
3. checkpoint를 전진시키지 않는 경우 다음 실행의 중복·무한 재시도 방지 정책을 확정한다.
4. valid 0/rejected N, valid N/rejected M, valid N/rejected 0을 각각 검증한다.

### 수정 범위 산정

- `src/pipelines/usedcar.py`
- Reject 저장·재처리 contract 및 테스트

## PIPE-012. 직접 `run_once()` 호출에서는 dry-run sink 검증이 생략됨

### 우선순위

**P2 — CLI와 Python API의 입력 검증 경계 불일치**

### 관련 구현

CLI는 argparse choice로 sink 값을 제한하지만, 직접 호출 경로는 pipeline별로 다르다.

- FAQ는 [faq.py:106](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/faq.py:106)에서 `not dry_run`일 때만 `sink_name`을 검사한다.
- Used-car는 [usedcar.py:58](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/usedcar.py:58)에서 dry-run이면 sink를 만들지 않아 unsupported sink가 검증되지 않는다.
- Registration은 [registration.py:58](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/registration.py:58)에서 dry-run 여부와 관계없이 sink 값을 검사한다.

### 영향

- 같은 외부 입력 오류가 pipeline과 실행 방식에 따라 성공 또는 실패가 된다.
- scheduler가 CLI 대신 `run_once()`를 호출할 때 잘못된 sink 설정을 조기에 발견하지 못한다.
- README의 sink 입력 계약이 CLI에만 적용되는지 직접 API에도 적용되는지 불명확하다.

### 승인 기준

1. `run_once()`를 public orchestration API로 볼지 CLI 전용 내부 함수로 볼지 결정한다.
2. public API라면 세 pipeline의 sink/mode/period 입력 검증을 동일하게 한다.
3. dry-run에서도 unsupported sink가 결정론적으로 실패하는지 테스트한다.

### 수정 범위 산정

- 세 pipeline의 입력 검증
- pipeline API contract test

## 4. 외부 파일에서 확인된 연관 사항 — 수정 범위 제외

아래 사항은 pipeline 점검 중 발견했지만 요청 대상인 `src/pipelines` 외부 파일의 문제이므로 본 보고서 작성 범위에서 수정하지 않는다.

### 4.1 기존 loading 이슈 문서의 checkpoint 설명이 현재 구현과 불일치

[docs/issues/loading_issues.md:220](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/docs/issues/loading_issues.md:220) 이후 문서에는 local JSON checkpoint 중심의 이전 상태가 남아 있다. 현재 pipeline·loading README는 SQL `pipeline_runs.progress_key`를 canonical checkpoint로 설명한다. 문서 정리는 별도 loading/documentation 작업으로 분리한다.

### 4.2 legacy Data Specification이 현재 pipeline 정책과 불일치

[docs/Data_Specification.md:16](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/docs/Data_Specification.md:16)은 중고차 테이블 수와 등록현황 API 3,000건·기간 보완 정책을 이전 기준으로 기술한다. 현재 [pipelines README:38](/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/src/pipelines/README.md:38)은 1초/500건 중고차 수집과 Registration 논리적 API 1회를 정의한다. 어느 문서가 canonical인지 별도 문서 기준선 결정이 필요하다.

## 5. 최종 판정

현재 상태는 다음과 같이 판정한다.

1. **JSONL fixture 정상 경로:** 확인
2. **pipeline 내부 import 경계 및 정적 검사:** 확인
3. **pipeline `run_once()` 모듈 단위 테스트 완결:** 확인 — `84 passed`
4. **stage별 local JSONL 관측성 계약:** 확인 — 정상 Validate event 및 stage/logic 실패 정보 반영
5. **Registration fixture dry-run 영속 부작용 없음:** 확인 — quota/state/sink 비영속
6. **Used-car snapshot·checkpoint 안정성:** fixture 기준 확인 — epoch 변경 시 중단, 마지막 성공 checkpoint 유지
7. **실제 SQL/Mongo 적재·Upsert 및 운영 로그:** 미실행
8. **Reject-only checkpoint 정책:** 조건부 미결 — business 결정 필요

따라서 사용자가 지정한 “해당 모듈 단위 테스트 결과가 온전히 나왔을 경우” 기준은 fixture/JSONL 범위에서 충족했다. 다만 실제 DB·live 운영 정상 승인은 수행하지 않았고, PIPE-003·PIPE-006·PIPE-011은 별도 결정 또는 검증이 필요하다.
