# 운영 테스트 및 데이터 정합성 이슈 보고서

- 작성일: 2026-08-13
- 대상 저장소: `/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3`
- 대상 모듈: `src/*`
- 참고 폴더: `/Users/ahh/bootcamp-study/70_Projects/mlo-01-p1-team3/ref/mlo-01-p1-team3-a`
- 목적: 전체 pipeline의 Mock·Live 운영 검증 결과, 수정 이력, 데이터 정합성, DB migration 및 실제 운영 관측 결과를 하나의 근거로 정리
- 완료 기준: 단위·Mock·Live 실행 결과가 온전히 출력되고, 실제 sink의 business key·Upsert·checkpoint·참조 무결성·cleanup 결과를 확인한 경우에만 완료로 판정
- 보고서 상태: 완료 — DB 초기화·migration 재현·5분 Live 관측 결과 반영
- 주의: 본 보고서는 실행 결과를 기록하며, Git commit 또는 원격 반영을 증명하지 않는다.

## 0. 현재 상태

| ID | 우선순위 | 항목 | 현재 판정 |
|---|---|---|---|
| OPS-001 | P0 | 전체 단위·Mock 테스트 | 해결 — Mock `98 passed`, 기본 전체 `191 passed, 7 skipped` |
| OPS-002 | P0 | 실제 MongoDB·MySQL Live 검증 | 해결 — Live 단독 7건 및 Live 포함 전체 198건 통과 |
| OPS-003 | P1 | 중고차 business key 기반 Upsert | 해결 — 미존재 insert, 동일 내용 unchanged, 업무값 변경 update 검증 |
| OPS-004 | P1 | 중고차 증분·checkpoint | 해결 — 부분 거부 진행, 전체 거부 중단, 빈 증분 유지, 비후퇴 및 transaction 경계 검증 |
| OPS-005 | P1 | 중고차 공유 dimension과 content hash | 해결 — sparse merge와 공유 dimension fan-out 재해시 반영 |
| OPS-006 | P1 | FAQ 동적 건수 및 Mongo 계약 | 해결 — 현재 24건을 관측했으나 고정 건수 없이 source 전체·unique index·validator·BSON Date 검증 |
| OPS-007 | P1 | 등록현황 집계 패턴 적재 | 해결 — `총계>*`, `*>계`를 preprocessing 단계에서 제외 |
| OPS-008 | P1 | resource cleanup·실패 보존 | 해결 — client/sink/quota close, cleanup 실패 시 원래 실패 보존 검증 |
| OPS-009 | P1 | 실제 DB 전면 초기화와 migration 재현 | 해결 — 임시 backup 후 애플리케이션 DB만 초기화하고 canonical schema 재생성 |
| OPS-010 | P1 | 초기화 후 5분 Live 관측 | 해결 — 정확히 300초, pipeline 15회 모두 종료코드 0, 중복·orphan·오류 0 |

## 1. 판정 기준

| 우선순위 | 의미 |
|---|---|
| P0 | 실행 증거가 없거나 핵심 pipeline을 정상으로 승인할 수 없는 차단 이슈 |
| P1 | 정상 경로가 실행되어도 데이터 손실·중복·checkpoint 오류·참조 무결성 훼손 가능성 때문에 반드시 해소해야 하는 이슈 |
| P1-조건부 | 운영 source 또는 정책 결정에 따라 차단 이슈로 승격될 수 있는 항목 |
| P2 | 핵심 적재는 유지되지만 관측성·문서·유지보수성을 저해하는 항목 |

데이터 정합성은 단순히 `N건 이상` 적재되었는지가 아니라 다음 계약으로 판정했다.

1. 저장소에 business key가 없으면 insert한다.
2. 동일 business content가 있으면 중복 write 없이 unchanged 처리한다.
3. business content가 변경되면 기존 key의 row/document를 update한다.
4. 적재 후 row 수와 distinct business key 수가 일치한다.
5. 중고차 정규화 테이블의 FK와 parent-child 참조에 orphan이 없다.
6. source sequence와 checkpoint가 성공 적재 이후에만 전진하며 역행하지 않는다.
7. pipeline별 수집·전처리·유효·거부·insert·update·unchanged·API 호출 수의 단위가 구분된다.

`application_logs` 테이블 적재는 현재 제품의 필수 운영 계약이 아니다. 해당 테이블에 로그가 적재되지 않는 상태는 정상으로 판정하며, pipeline 정상 여부는 반환 상태, JSONL event, `pipeline_runs` 및 최종 데이터 정합성으로 판단한다.

## 2. 최종 테스트 실행 증거

모든 Python 명령은 Conda `sandbox` 환경에서 `python -m pytest`로 실행했다.

| 검증 | 결과 | 의미 |
|---|---:|---|
| Mock 전체 | `98 passed in 0.42s` | 외부 network 차단, adapter·transaction·retry·cleanup·checkpoint 계약 검증 |
| 기본 전체 | `191 passed, 7 skipped in 0.53s` | Live 환경변수 미설정 시 7건 의도적 skip, 그 외 전체 성공 |
| 실제 격리 Live 단독 | `7 passed` | 실제 API와 격리 MongoDB·MySQL에 write/readback 수행 |
| Live 포함 전체 | `198 passed in 14.17s` | 동일 최종 snapshot에서 단위·Mock·Live 전체 성공 |
| Ruff | `All checks passed!` | `src`, `tests` 정적 검사 성공 |
| Compile | 성공 | `python -m compileall -q src tests` 성공 |
| Diff whitespace | 성공 | `git diff --check` 성공 |
| 격리 DB cleanup | SQL 0개, MongoDB 0개 | `mlo_live_test_*` DB가 실행 후 남지 않음 |

위 Live 테스트는 임시 격리 DB를 생성하고 실제 source와 sink를 사용한 검증이다. 운영 DB를 직접 비우고 재구성한 뒤 장시간 운용한 결과는 아래 별도 절에 구분한다.

## 3. pipeline별 데이터 정합성 결과

### 3.1 FAQ

- 현재 Live source에서는 24건이 관측되었다.
- 제품 계약과 테스트는 24를 고정값으로 사용하지 않고 실제 수집 결과의 전체 건수를 기준으로 한다.
- 최초 적재는 insert, 동일 source 재적재는 unchanged, 같은 `faq_id`의 내용 변경은 update로 검증했다.
- MongoDB `uq_faq_id` unique index, brand/category 및 updated_at index, strict validator를 검증했다.
- `source_updated_at`, `collected_at`, `created_at`, `updated_at`은 BSON Date로 readback했다.
- 내부에서 생성한 `ApiClient`는 성공·실패 모두 닫고, 외부에서 주입한 client의 수명은 호출자에게 유지한다.

### 3.2 중고차

- `listing_id`를 listing business key로 사용한다.
- 미존재 listing은 insert하고, 동일 canonical business content는 unchanged 처리한다.
- listing 업무값 또는 공유 dimension의 업무값이 변경되면 update 및 canonical hash 재계산을 수행한다.
- 새 event ID·sequence만 전달된 동일 business content는 unchanged로 집계하면서 source event metadata는 보존한다.
- sparse incremental payload는 기존 DB 값과 병합한 최종 row를 기준으로 hash를 계산한다.
- brand, model, location, dealer, business area, parent business area가 변경되면 해당 dimension을 참조하는 배치 밖 listing까지 fan-out 재해시한다.
- `source_updated_at`처럼 listing별로 달라질 수 있는 dimension metadata는 dimension의 business 변경으로 오판하지 않는다.
- `vehicle_models → vehicle_brands`, business-area self reference, listing의 model/location/dealer/business-area FK와 orphan 0건을 검증했다.

### 3.3 등록현황

- business key는 `report_month + sido_name + sigungu_name + vehicle_type + usage_type`이다.
- `vehicle_type == "총계"` 또는 `usage_type == "계"`인 지표는 quantity 검증과 hash 계산 전에 제외한다.
- 5개 차종 × 4개 용도 형태의 입력에서는 집계 8개를 제외하고 세부 12개만 적재한다.
- 최초 적재 insert, 동일 입력 unchanged, 세부 지표 수량 변경 1건 update 및 나머지 unchanged를 검증했다.
- Live 예상 건수는 고정 숫자가 아니라 source에서 발견한 비집계 `차종>용도` key 수로 동적으로 계산한다.

## 4. checkpoint·거부·실패 처리 계약

### 4.1 부분 거부와 전체 거부

- 일부 row만 거부되면 오류 로그를 남기고 유효 row를 적재한 뒤 source checkpoint를 진행한다.
- page의 모든 row가 거부되면 batch를 실패 처리하고 sink save와 checkpoint 진행을 모두 중단한다.
- 전체 거부 batch는 source 또는 preprocessing이 수정될 때까지 같은 위치에서 반복 실패할 수 있다. 이는 poison row를 버리지 않고 데이터 유실을 방지하기 위한 확정 정책이다.
- source가 정상적으로 빈 page를 반환한 steady state는 성공으로 처리하고 기존 checkpoint를 유지한다.

### 4.2 checkpoint transaction

- SQL checkpoint를 canonical source로 사용하고 local JSON을 fallback으로 사용한다.
- 중고차 data batch 적재와 `pipeline_runs.progress_key` 기록은 같은 transaction에서 수행한다.
- initial finalization이 실패하면 local checkpoint를 만들지 않는다.
- 이전 committed `after_seq`보다 작은 source sequence는 initial/incremental mode와 관계없이 load 전에 차단한다.
- multi-batch Live 실행에서 batch별 count 합계, API 호출 수, 각 progress key와 마지막 local checkpoint를 대조했다.

### 4.3 cleanup 및 오류 보존

- FAQ, 중고차, 등록현황은 성공을 기록하기 전에 필수 resource close를 완료한다.
- close 자체가 실패하면 `resource_close_failed`를 기록하고 성공으로 오표현하지 않는다.
- 본래 collect/save 오류와 cleanup 오류가 동시에 발생하면 본래 오류 객체와 error code를 보존한다.
- 등록현황 sink와 quota close는 하나가 실패해도 둘 다 시도한다.
- 사용자 설정의 credential, URI, API key 원문은 테스트 출력과 로그에 기록하지 않았다.

## 5. 검토 중 발견한 주요 실패와 수정

### OPS-F01. 동일 중고차 재적재가 update로 오분류됨

- 증상: Live initial 50건을 동일하게 다시 적재했을 때 `unchanged=1`, `updated=49`가 기록되었다.
- 원인: 여러 listing이 공유하는 dimension의 `source_updated_at`에 각 listing의 timestamp를 넣고, 이를 dimension business 변경으로 비교했다.
- 영향: 실제 내용이 같은 재실행이 대량 update로 보이고 불필요한 write와 잘못된 운영 지표를 만들었다.
- 조치: dimension metadata와 business columns를 분리하고 canonical hash 비교 및 fan-out 재해시 범위를 수정했다.
- 재검증: 동일 source ID와 hash의 재실행이 전건 unchanged로 통과했다.
- side effect: 실패는 격리 DB에서 재현되어 운영 DB 데이터에는 영향을 주지 않았다.

### OPS-F02. sparse payload의 hash와 최종 DB row 불일치 가능성

- 증상: SQL은 누락 값을 `COALESCE`로 보존하지만 incoming sparse payload만으로 hash를 만들 수 있었다.
- 영향: DB에 저장된 최종 aggregate와 `content_hash`가 다른 상태가 되어 이후 unchanged/update 판정이 흔들릴 수 있었다.
- 조치: 기존 DB row와 sparse payload를 병합한 canonical aggregate를 기준으로 hash를 다시 계산한다.

### OPS-F03. 공유 dimension 변경 시 배치 밖 listing hash가 stale해짐

- 증상: 한 listing을 통해 공유 dimension 이름이 변경되면 같은 dimension을 참조하지만 현재 batch에 없는 listing의 aggregate도 바뀐다.
- 영향: 해당 listing들의 content hash가 영구적으로 오래된 값으로 남을 수 있었다.
- 조치: 변경 dimension을 참조하는 전체 listing key를 조회해 같은 transaction에서 fan-out 재해시한다.

### OPS-F04. 초기 watermark API call 관측 누락

- 증상: initial mode의 watermark 호출은 실제 API count에 포함되지만 batch별 `pipeline_runs.api_calls` 합계에는 포함되지 않았다.
- 영향: DB 관측 count 합계가 실제 외부 호출보다 1 적었다.
- 조치: initial finalization row에 watermark call을 합산하고 Live에서 pipeline 결과와 DB 합계를 대조했다.

### OPS-F05. 집계 등록현황이 세부 데이터와 함께 적재됨

- 증상: `총계>*`, `*>계` row가 세부 지표와 같은 테이블에 적재되었다.
- 영향: 합계와 세부를 함께 합산하면 이중 집계가 발생한다.
- 조치: preprocessing에서 두 패턴을 모두 제외한다.
- 이전 운영 상태: 읽기 전용 확인 당시 기존 집계 row의 union은 2,208건이었다. 신규 입력 차단만으로 기존 row가 자동 삭제되지는 않는다.

## 6. Sub Agent 검토 결과

Reviewer는 가용 모델 제한으로 5.6 Sol Max를 사용했다.

| 검토 영역 | 최종 판정 | 독립 실행 증거 |
|---|---|---|
| pipeline·adapter 정합성 | APPROVED | 집중 118건, 기본 전체 191건+Live skip 7건, Live 7건 통과 |
| 격리·cleanup·credential | APPROVED | FAQ+Mock 106건, Mock 98건, 기본 전체 191건+Live skip 7건 통과 |

검토 과정에서 제기된 P0~P2 항목은 수정과 재검토를 반복했으며 최종 잔여 actionable finding은 없었다.

## 7. DB migration·전면 초기화 결과

### 7.1 삭제 대상과 백업

설정과 DB metadata를 먼저 읽은 뒤 다음 애플리케이션 객체만 삭제했다. MySQL 시스템 DB `mysql`, `information_schema`, `performance_schema`, `sys`와 MongoDB 시스템 DB `admin`, `config`, `local`은 제외했다.

| 저장소 | 삭제 대상 | 삭제 전 상태 |
|---|---|---|
| MySQL `sales_support_db` | `api_quota_usage`, `pipeline_runs`, `schema_migrations`, `vehicle_brands`, `vehicle_business_areas`, `vehicle_dealers`, `vehicle_listings`, `vehicle_locations`, `vehicle_models`, `vehicle_registration_reports` | 순서대로 2, 11, 1, 12, 1,248, 933, 1,452, 49, 50, 5,520행 |
| MongoDB `support_db` | `faq` collection | 24 documents |

초기 사용자 요청에 따라 당시 `application_logs.application_logs` 47행도 삭제했다. 이후 지시자 결정으로 이 table 적재는 정상 동작의 필수 계약에서 제외했고 최종 migration에서도 완전히 제거했다. 이미 DB에 생성된 빈 `application_logs.application_logs`는 추가 파괴 작업 없이 0행 상태로 남겼다.

삭제 직전 임시 복구 지점을 만들었다.

| 파일 | 크기 | SHA-256 |
|---|---:|---|
| `/private/tmp/mlo-db-backup-20260813-s9gwfB/mysql-app-databases.sql` | 3,236,070 bytes | `aaa3eb19343849d05e05acb7c9cc136334e2ae410b310a77e4fbe3fd258337f7` |
| `/private/tmp/mlo-db-backup-20260813-s9gwfB/mongodb-support-db.archive.gz` | 6,259 bytes | `f1419f7cc9a9204db0bdc3f0520c0251f61beaa1382ea917c5bb69928d02ce3a` |

위 파일은 `/private/tmp`의 임시 backup이다. OS가 정리하면 삭제 전 데이터는 복구할 수 없으므로 영구 backup으로 간주하면 안 된다.

### 7.2 migration 구현과 적용 결과

- `migrations/sql/rebuild.py`: exact confirmation, canonical `sales_support_db` 고정, 시스템·비canonical·unsafe identifier 차단 후 table 삭제와 forward migration 재적용
- `migrations/mongo/rebuild.py`: exact confirmation, `admin/config/local` 차단, app DB의 비시스템 collection 삭제 후 FAQ migration 재적용
- `migrations/sql/V001__mvp_schema.sql`: `sales_support_db`의 10개 table, 6개 FK, unique/index 생성. `application_logs` 관련 DB·table DDL은 제거
- `migrations/mongo/ensure_indexes.py`: FAQ strict/error validator, BSON Date 계약, unique 및 secondary index 보장

| 검증 | 결과 |
|---|---|
| SQL V001 statement | 12개 |
| V001 SHA-256 | `aefd54fe73ab308847de0dc81fba8b60ec51de4729db12c9089e9bac03d2f241` |
| migration ledger | 실제 schema 대조 후 checksum 일치, runner 재진입 `status=OK`, `applied=[]` |
| MySQL FK | 6개 readback 정상 |
| Mongo validator | canonical validator exact match, `strict/error` |
| Mongo index | `_id_`, `uq_faq_id`, `ix_faq_brand_category`, `ix_faq_updated_at` |
| 비테스트 검증 | migration compile, Ruff, SQL parse, guard smoke, diff-check 통과 |

DB별 관계·table/collection 존재 당위성·grain·key·index 상세는 다음 문서에 분리했다.

- `docs/MySQL_Migration_and_Live_Operation_Report_2026-08-13.md`
- `docs/MongoDB_Migration_and_Live_Operation_Report_2026-08-13.md`

## 8. 초기화 후 5분 Live 관측 결과

### 8.1 관측 계약

- 시작: `2026-08-13T13:51:53+09:00`
- 종료: `2026-08-13T13:56:53+09:00`
- 경과: 정확히 `300.0s`
- 방식: 매 분 `python -m src.main --profile live --once`로 registration → usedcar → FAQ 순서 실행
- 실행: pipeline별 5회, 총 15 invocation, 모두 return code 0
- 참고: 최초 monitor launcher 한 번은 import path 오류로 pipeline 호출 전 즉시 종료했다. DB write와 관측 창이 시작되지 않았으므로 경로를 수정하고 새로운 300초 창을 처음부터 다시 측정했다.
- 관측 종료 후 `src/main.py`를 갱신해 `--profile live`가 기본 60초 간격으로 계속 실행되도록 했다. 이 절은 변경 전 명시적 `--once` 호출로 확보한 300초 증거이며, 현재 운영에서는 `--once`를 생략하면 main process가 반복 실행을 직접 소유한다.

### 8.2 실행별 적재 결과

| 회차 | Registration | Usedcar | FAQ |
|---:|---|---|---|
| 1 | collected/valid/rejected `0/0/0`, API 1 | initial 10,000건 insert, reject 0, API 21, checkpoint 24,356 | 24 insert, reject 0 |
| 2 | `0/0/0`, API 1 | incremental 28건 insert, reject 0, API 1, checkpoint 24,384 | 24 unchanged |
| 3 | `0/0/0`, API 1 | steady state 0건, checkpoint 24,384 | 24 unchanged |
| 4 | `0/0/0`, API 1 | steady state 0건, checkpoint 24,384 | 24 unchanged |
| 5 | `0/0/0`, API 1 | steady state 0건, checkpoint 24,384 | 24 unchanged |

- Usedcar 합계: collected/valid/inserted 10,028, rejected/update/unchanged 0
- FAQ 합계: collected/valid 120, inserted 24, unchanged 96, rejected/update 0
- Registration 합계: API 5, quota used 5, source data와 reject 0

등록현황은 현재월 `2026-08` source가 다섯 번 모두 정상 0건을 반환했다. migration 또는 write 실패는 아니지만 이 관측 창에서는 registration insert/unchanged/update를 실데이터로 다시 입증하지 못했다. 실제 게시 데이터가 있는 기준월을 지정하는 freshness 정책이 필요하며 이번 작업에서는 보고만 하고 `src`를 수정하지 않았다.

### 8.3 종료 시 데이터 정합성

| 항목 | 결과 |
|---|---:|
| MySQL listing | 10,028 |
| Listing business key 중복 | 0 |
| Registration composite key 중복 | 0 |
| 등록현황 `총계>*` 또는 `*>계` | 0 |
| Model-brand/listing dimension/business-area self orphan | 전 항목 0 |
| Checkpoint | `24356 → 24384 → 24384 → 24384 → 24384`, 비후퇴 |
| Mongo FAQ | 24 documents, duplicate `faq_id` 0 |
| Mongo validator/index 누락 | 0 |
| JSONL event | INFO 156, ERROR 0 |
| credential·URI 의심 pattern | 0 |
| 종료 후 monitor·pipeline process | 0 |

이번 300초 창에는 실제 source 변경 event가 없어 usedcar와 FAQ의 update는 0이었다. 이는 update 실패가 아니라 변경 입력이 없었다는 관측 결과이며, 변경 Upsert 계약은 앞선 Mock·격리 Live 검증에서 확인했다.

## 9. 잔여 이슈 및 운영 주의사항

1. 전체 거부 batch는 checkpoint를 유지하므로 원천 또는 변환 규칙이 수정될 때까지 재시도 시 반복 실패한다.
2. Live source는 실행 사이에 변경될 수 있다. idempotency는 단순히 매번 동일한 insert/update 숫자가 아니라 business key 중복 여부, 최종 content hash, 변경 입력의 update 여부로 판정해야 한다.
3. DB 전면 초기화 전 dump는 `/private/tmp`에만 있어 영구 복구 수단이 아니다.
4. `application_logs`는 필수 sink에서 제외하는 것으로 결정했으며 SQL migration에서도 생성하지 않는다. 이미 생성된 빈 DB·테이블의 실제 잔존 여부는 7절에 별도로 기록한다.
5. 현재 작업 트리는 여러 수정 및 신규 파일을 포함하고 있으며 Git commit·push 여부는 별도 확인이 필요하다.
6. `src/*` 밖에서 발견한 문제는 본문에 보고하되 별도 요청 없이 수정 범위를 확장하지 않는다.

## 10. 최종 판정

Mock·격리 Live·실제 DB migration 재현·초기화 후 정확히 5분 Live 관측을 모두 완료했다. 15회 invocation의 실행 오류, business key 중복, FK orphan, checkpoint 역행, Mongo validator/index 불일치는 모두 0이므로 전체 운영 검증은 **APPROVED**이다.

단, 현재월 등록현황 source가 0건이어서 이번 5분 창에서는 registration 실데이터 Upsert를 재입증하지 못했다. 이는 pipeline 실패가 아닌 source freshness 경계이며, 게시 데이터가 있는 기준월을 선택하는 운영 정책의 후속 확인 대상으로 남긴다.
