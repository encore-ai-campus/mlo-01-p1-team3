# PRD · 자동차 등록·FAQ 데이터 파이프라인

> starter_id: `encore.chapter1.brd-prd-requirements-workshop.starter`  
> starter_version: `v1`  
> 작성 규칙: `TODO-LEARNER` 여섯 행과 대표 AC 세 개를 먼저 완성한다.

- document_id: `PRD-VF-001`
- version: `v1`
- document_state: `Review`
- brd_reference: `BRD-VF-001@v1`
- source_registry_reference: `config/source-registry.yml@v1`
- owner_role: `<TODO>`
- reviewer_roles: [`<TODO>`]

## 1. 제품 정의와 사용자 필요

제품은 조회 가능한 자동차·FAQ 데이터셋, 반복 실행 가능한 pipeline, 작은 JSON 인계 snapshot이다. 웹 dashboard·UI와 ML 모델은 제품 범위가 아니다.

| ID | 사용자 필요 |
|---|---|
| `UN-AN-001` | 분석 담당자는 기준월·지역·차종별 자동차 결과와 출처를 확인하고 싶다. |
| `UN-FAQ-001` | FAQ 사용자는 회사·category별 질문·답변과 출처를 확인하고 싶다. |
| `UN-OPS-001` | 운영 담당자는 한 명령 실행·안전한 재실행·실패 지점 확인을 원한다. |
| `UN-AUD-001` | 검토자는 source·품질·처리 결과를 evidence로 감사하고 싶다. |

## 2. 요구사항 catalog

| ID | 상태 | 요구사항 | BRD·사용자 필요 | AC | owner | due |
|---|---|---|---|---|---|---|
| `FR-VEH-COLLECT-001` | Must do | 승인 registry에서 선택 기준월 자동차 raw를 수집한다. | `TODO-LEARNER` | `TODO-LEARNER` | collector | Day 22 |
| `FR-VEH-TRANSFORM-001` | Must do | 승인 raw의 wide measure를 long candidate로 변환한다. | `TODO-LEARNER` | `TODO-LEARNER` | transformer | Day 22 |
| `FR-FAQ-COLLECT-001` | Must do | allowlist FAQ page만 요청 상한 안에서 수집한다. | `BR-OBJ-002`·`UN-FAQ-001` | `AC-FAQ-COLLECT-001` | collector | Day 22 |
| `FR-RUN-001` | Must do | 같은 entry point로 fixture 1회 실행을 시작한다. | `BR-OBJ-003`·`UN-OPS-001` | `AC-RUN-001` | pipeline | Day 21 |
| `FR-VEH-LOAD-001` | Must do | 유효 vehicle record를 MySQL에 upsert한다. | `BR-OBJ-001`·`UN-AN-001` | `AC-VEH-LOAD-001` | repository | Day 22 |
| `FR-FAQ-LOAD-001` | Must do | 유효 FAQ document를 MongoDB에 upsert한다. | `BR-OBJ-002`·`UN-FAQ-001` | `AC-FAQ-LOAD-001` | repository | Day 22 |
| `FR-QUERY-001` | Must do | 자동차 집계와 FAQ company·category 조회 결과를 제공한다. | `BR-OBJ-001`·`BR-OBJ-002`·`UN-AN-001`·`UN-FAQ-001` | `AC-QUERY-001` | query | Day 23 |
| `FR-SCHEDULE-001` | Must do | 수동 성공 뒤 fixture 예약 실행을 한 번 수행한다. | `BR-OBJ-003`·`UN-OPS-001` | `AC-SCHEDULE-001` | scheduler | Day 23 |
| `DR-VEH-001` | Must do | six-field key·비음수 count·source provenance를 보장한다. | `TODO-LEARNER` | `TODO-LEARNER` | data-quality | Day 22 |
| `DR-FAQ-001` | Must do | identity·content hash·license·attribution을 보존한다. | `TODO-LEARNER` | `TODO-LEARNER` | data-quality | Day 22 |
| `NFR-IDEMP-001` | Must do | 동일 입력 재실행이 business row를 중복 추가하지 않는다. | `TODO-LEARNER` | `TODO-LEARNER` | pipeline | Day 23 |
| `NFR-SOURCE-001` | Must do | robots·license·allowlist·schema 경계가 불명확하거나 바뀌면 write 없이 중단한다. | `TODO-LEARNER` | `TODO-LEARNER` | collector | Day 22 |
| `NFR-SECRET-001` | Must do | credential·private endpoint를 tracked file과 log에 남기지 않는다. | `BR-OBJ-004`·`UN-AUD-001` | `AC-SECRET-001` | reviewer | Day 21~23 |
| `NFR-OBS-001` | Must do | run·stage 상태와 단위별 count·sanitized error를 기록한다. | `BR-OBJ-003`·`BR-OBJ-004`·`UN-AUD-001` | `AC-OBS-001` | pipeline | Day 23 |
| `NFR-RETRY-001` | Must do | retry 가능한 transport·HTTP 오류만 정해진 횟수 안에서 재시도한다. | `BR-OBJ-003`·`UN-OPS-001` | `AC-RETRY-001` | pipeline | Day 23 |

`TODO-LEARNER`가 있는 FR 2행·DR 2행·NFR 2행이 `REQ-M01`의 대표 요구 6개다.

## 3. Acceptance criteria

| AC ID | Given | When | Then | Evidence | due | evidence_status |
|---|---|---|---|---|---|---|
| `AC-VEH-COLLECT-001` | official-shape vehicle fixture | 기준월 collector 실행 | 성공 body와 raw checksum 기록 | `evidence/day22-evidence.md` | Day 22 | planned |
| `AC-VEH-TRANSFORM-001` | wide measure fixture | transformer 실행 | 차종·용도 long candidate 생성 | `output/<run_id>/quality-report.json` | Day 22 | planned |
| `AC-FAQ-COLLECT-001` | 허용 robots·license·page fixture | FAQ collector 실행 | allowlist·상한 안에서만 raw 저장 | `evidence/day22-evidence.md` | Day 22 | planned |
| `AC-RUN-001` | vehicle·FAQ fixture 각 1건 | fixture entry point 1회 실행 | exit 0, stage별 `1=1+0` | `evidence/day21-smoke.txt` | Day 21 | planned |
| `AC-VEH-LOAD-001` | 유효 vehicle candidate | MySQL load | 유효 고유 key와 target key 차이 0 | `output/<run_id>/quality-report.json` | Day 22 | planned |
| `AC-FAQ-LOAD-001` | 유효 FAQ candidate | MongoDB load | unique `faq_id` 위반 0, target 차이 0 | `evidence/day22-evidence.md` | Day 22 | planned |
| `AC-QUERY-001` | fixture 적재 완료 | 지정 SQL·Mongo query 실행 | 두 expected 결과와 일치 | `evidence/final-verification.md` | Day 23 | planned |
| `AC-SCHEDULE-001` | 수동 fixture run 성공 | 가까운 시각 예약 | `trigger=scheduled` run 1개 뒤 scheduler 중지 | `evidence/scheduler-run.md` | Day 23 | planned |
| `AC-VEH-DATA-001` | `<TODO: 정상 vehicle 입력>` | `<TODO: quality·load 실행>` | `<TODO: null·duplicate·target 값>` | `<TODO: 정확한 경로>` | Day 22 | planned |
| `AC-FAQ-DATA-001` | FAQ fixture | transform·load·query | identity·license·attribution 누락 0 | `evidence/day22-evidence.md` | Day 22 | planned |
| `AC-IDEMP-001` | `<TODO: 동일 checksum 입력>` | `<TODO: 두 번 실행>` | `<TODO: before·after count>` | `<TODO: 정확한 경로>` | Day 23 | planned |
| `AC-SOURCE-001` | `<TODO: robots·license·allowlist·schema 실패>` | `<TODO: collector 실행>` | `<TODO: 우회·write·sanitized 상태>` | `<TODO: 정확한 경로>` | Day 22 | planned |
| `AC-SECRET-001` | 제출 후보 전체 | tracked file·log scan | credential·private endpoint 의심 0 | `evidence/requirements-review.md` | Day 23 | planned |
| `AC-OBS-001` | 성공·실패 fixture | pipeline 실행 | run·stage 상태와 sanitized error 기록 | `logs/sanitized-success.jsonl`, `evidence/retry-idempotency.md` | Day 23 | planned |
| `AC-RETRY-001` | timeout·503·비재시도 fixture | retry wrapper 실행 | retry 대상만 최대 3회, 나머지 즉시 종료 | `evidence/retry-idempotency.md` | Day 23 | planned |

`REQ-M02`에서는 `AC-VEH-DATA-001`, `AC-IDEMP-001`, `AC-SOURCE-001`의 TODO를 완성한다.

## 4. 의존성·fallback·실패 경계

- source 세부 정본: `config/source-registry.yml@v1`
- field·business key 정본: `docs/data-contract.md@v1`
- 구조 정본: `docs/architecture.md@v1`
- live 승인 실패 시 Must 경로: official-shape fixture 또는 승인된 공식 file
- robots·license·allowlist·schema 경계 실패 시: 우회와 DB write 없이 중단

## 5. Out of scope와 미결 질문

- 웹 dashboard·UI, ML, production HA·DR, CAPTCHA 우회는 제외한다.
- Day 23의 작은 `output/sample/dashboard.json`은 인계 snapshot으로 포함한다.
- source 검증 전에는 `document_state: Review`를 유지한다.

## 6. Review와 baseline

| reviewed_at | reviewer_role | review_result | source_registry_version | note |
|---|---|---|---|---|
| `<TODO>` | `<TODO>` | `PASS | FAIL` | `v1` | `<TODO>` |

source registry 확인 뒤에만 `document_state: Baselined`로 바꾼다.
