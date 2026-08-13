# PRD · 중고차 데이터 수집·전처리·운영 MVP

- document_id: PRD-MLO-001
- version: v3
- document_state: Review
- brd_reference: BRD-MLO-001@v3
- source_registry_reference: docs/07_source-registry.md@v2
- data_contract_reference: docs/05_Data Specification.md@v2
- architecture_reference: docs/06_architecture.md@v1
- implementation_reference: docs/00_implementation.md@v1
- baseline_date: <TODO: YYYY-MM-DD>
- provenance: 사용자 제공 MVP 요구사항과 ref/brd-prd-requirements-workshop 기준 문서
- owner_role: <TODO>
- reviewer_roles: [<TODO>]

## 1. 제품 정의와 사용자 필요

제품은 세 가지 외부 데이터 Source를 반복 실행 가능한 Pipeline으로 수집·전처리·검증·저장하고, Backend 운영자가 Run·stage·logic 상태를 Dashboard와 Evidence로 확인할 수 있는 MVP다. 사용자용 검색·BI·AI 화면은 후속 범위이며, MVP의 결과는 SQL·MongoDB에 저장된 최신 데이터와 운영 인계 정보다.

| ID | 사용자 필요 |
|---|---|
| UN-OPS-001 | 운영자는 한 번의 실행 결과에서 성공·실패·Skip·재실행 필요 여부를 확인하고 싶다. |
| UN-OPS-002 | 운영자는 중고차 마지막 성공 Checkpoint와 1초·500건 처리 결과를 확인하고 싶다. |
| UN-DATA-001 | 데이터 담당자는 동일 입력을 안전하게 재처리하고 Business Key 중복을 검증하고 싶다. |
| UN-SALES-001 | 영업 담당자는 최신 매물과 자동차등록현황보고의 Source·기준일을 확인하고 싶다. |
| UN-FAQ-001 | 고객지원 담당자는 FAQ 질문·답변·분류·출처의 최신 상태를 확인하고 싶다. |
| UN-AUD-001 | 검토자는 Source·품질·로그·알림에 민감정보가 없는지 Evidence로 확인하고 싶다. |

## 2. 제품 범위와 실행 기준

### 2.1 Source·Schedule

| Pipeline | Source | Schedule | 처리 기준 | 저장 |
|---|---|---|---|---|
| FAQ | http://192.168.0.51:4000/ FAQ 영역 | 매일 09:00 KST | HTML → Document | MongoDB Upsert |
| 중고차 | http://192.168.0.51:4000/ API | 1초마다 장기 실행 Worker | 1회 최대 500건, 초기 1만건이면 20회, 이후 증분 | 참조 5개 테이블 선 Upsert 후 `vehicle_listings` Insert/Upsert |
| 자동차등록현황보고 | 등록현황보고 API | 매일 1회 | 실행당 1회, `formList` 전체 지표 분해, 일일 3,000회 초과 방지 | SQL Upsert |

중고차 1초 주기는 cron으로 구현하지 않는다. Backend의 장기 실행 Python Worker가 단일 실행 주체가 되고, Shell Script가 시작·환경 확인·비정상 종료 재시작을 담당한다. Worker는 요청을 겹쳐 보내지 않으며, 초기 1만건을 500건씩 최대 20회 순차 처리한다.

### 2.2 AWS 실행 경계

| 호스트 | 수량 | 책임 |
|---|---:|---|
| Bastion | 1 | 운영자 SSH 진입·포트 포워딩 |
| Backend | 1 | Python Worker·Pipeline·Dashboard·로그·Discord |
| SQL | 1 | 정형 데이터·Run·quota·애플리케이션 로그 |
| MongoDB | 1 | FAQ Document |

DB와 Backend 운영 접근은 Bastion을 경유한다. SQL은 향후 Primary–Replica, MongoDB는 향후 3노드 Replica Set과 과반수 투표·Primary 선출로 확장할 수 있어야 하지만, 실제 HA는 MVP에 포함하지 않는다.

## 3. 요구사항 catalog

| ID | 상태 | 요구사항 | BRD·사용자 필요 | AC | owner | due |
|---|---|---|---|---|---|---|
| FR-ARCH-001 | Must do | Python·Shell Script·SQL·MongoDB·AWS와 Bastion 1, Backend 1, SQL 1, MongoDB 1의 고정 MVP 구성을 사용한다. | BR-OBJ-006·UN-OPS-001 | AC-ARCH-001 | infra | Day 1 |
| FR-ACCESS-001 | Must do | 운영자의 Backend·SQL·MongoDB 접근은 Bastion을 경유하고 Dashboard는 Tunnel로만 연다. | BR-OBJ-006·UN-OPS-001 | AC-ACCESS-001 | infra | Day 1 |
| FR-FAQ-COLLECT-001 | Must do | 허용된 FAQ 영역을 매일 09:00 KST에 수집하고 Source·license 정책이 불명확하거나 구조가 다르면 write 없이 중단한다. | BR-OBJ-001·UN-FAQ-001 | AC-FAQ-COLLECT-001 | FAQ collector | Day 2 |
| FR-FAQ-TRANSFORM-001 | Must do | FAQ 비정형 응답을 faq_id·question·answer·category·source·run·content hash·license·attribution 정보가 있는 MongoDB Document로 변환한다. | BR-OBJ-001·UN-FAQ-001 | AC-FAQ-TRANSFORM-001 | FAQ transformer | Day 2 |
| FR-FAQ-LOAD-001 | Must do | FAQ를 faq_id 기준 MongoDB Upsert하고 동일·변경·Reject 결과를 구분한다. | BR-OBJ-001·UN-FAQ-001 | AC-FAQ-LOAD-001 | FAQ repository | Day 2 |
| FR-LIST-COLLECT-001 | Must do | 중고차 API를 1초마다 순차 호출하고 1회 최대 500건을 처리한다. 초기 1만건은 20회 기준으로 수집한다. | BR-OBJ-002·UN-OPS-002 | AC-LIST-COLLECT-001 | vehicle collector | Day 2 |
| FR-LIST-INCREMENT-001 | Must do | 마지막 성공 sequence·updated_at·cursor 중 Source 계약값 이후의 중고차만 요청하고 적재 성공 후 Checkpoint를 전진한다. | BR-OBJ-002·UN-OPS-002·UN-DATA-001 | AC-LIST-INCREMENT-001 | vehicle pipeline | Day 2 |
| FR-LIST-TRANSFORM-001 | Must do | 중고차 API 응답을 매물 본체와 브랜드·모델·소재지·딜러·업무영역의 관계형 준비 계약으로 변환하고 각 엔터티의 안정 ID와 provenance를 검증한다. | BR-OBJ-002·UN-DATA-001 | AC-LIST-TRANSFORM-001 | vehicle transformer | Day 2 |
| FR-LIST-LOAD-001 | Must do | 중고차 참조 테이블을 먼저 Upsert한 뒤 `vehicle_listings`를 `listing_id` 기준으로 같은 transaction에서 최초 Insert·변경 Upsert한다. | BR-OBJ-002·UN-SALES-001 | AC-LIST-LOAD-001 | vehicle repository | Day 2 |
| FR-REG-COLLECT-001 | Must do | 자동차등록현황보고를 매일 1회 호출하고 요청 월(`start_dt=end_dt=YYYYMM`)의 `formList` 응답을 수집한다. 일일 3,000회는 초과 방지 quota로 기록한다. | BR-OBJ-003·UN-SALES-001 | AC-REG-COLLECT-001 | registration collector | Day 2 |
| FR-REG-TRANSFORM-001 | Must do | 등록현황 API의 각 `formList` 행을 월·시도명·시군구·차량구분·용도구분·수량 Row로 모두 분해하고 Source·run 정보를 추가한다. | BR-OBJ-003·UN-DATA-001 | AC-REG-TRANSFORM-001 | registration transformer | Day 2 |
| FR-REG-LOAD-001 | Must do | 등록현황을 `(report_month, sido_name, sigungu_name, vehicle_type, usage_type)` Business Key로 SQL Upsert한다. | BR-OBJ-003·UN-SALES-001 | AC-REG-LOAD-001 | registration repository | Day 2 |
| FR-PIPE-STAGE-001 | Must do | 모든 Pipeline은 Collect → Preprocess → Validate → Load 단계와 단계별 count·error 경계를 가진다. | BR-NEED-001·BR-OBJ-004 | AC-PIPE-STAGE-001 | pipeline | Day 2 |
| FR-OPS-LOG-001 | Must do | Backend는 Run·stage·logic별 로그를 SQL application_logs와 구조화 파일에 기록한다. | BR-OBJ-004·UN-OPS-001·UN-AUD-001 | AC-OPS-LOG-001 | pipeline | Day 3 |
| FR-OPS-DASH-001 | Must do | Python Dashboard에서 세 Pipeline 상태·최근 Run·단계 count·DB 상태·등록현황 quota·최근 오류를 보여준다. | BR-OBJ-004·UN-OPS-001 | AC-OPS-DASH-001 | pipeline | Day 3 |
| FR-OPS-DISCORD-001 | Must do | Pipeline 실패·DB 오류·quota 오류·Schema 오류를 민감정보 없는 Discord 요약으로 전파한다. | BR-OBJ-005·UN-OPS-001·UN-AUD-001 | AC-OPS-DISCORD-001 | pipeline | Day 3 |
| FR-OPS-SCHEDULE-001 | Must do | FAQ·등록현황은 Shell/cron으로, 중고차는 Shell이 관리하는 장기 Worker로 실행한다. | BR-OBJ-004·UN-OPS-001 | AC-OPS-SCHEDULE-001 | scheduler | Day 3 |
| FR-OPS-ISOLATE-001 | Must do | FAQ·중고차·등록현황 Pipeline은 독립 Run으로 실행되며 한 Pipeline 실패가 다른 Pipeline을 중단시키지 않는다. | BR-OBJ-004·UN-OPS-001 | AC-OPS-ISOLATE-001 | pipeline | Day 3 |
| DR-KEY-001 | Must do | FAQ·중고차·등록현황의 Business Key와 Source·collected_at·run_id provenance를 보존한다. | BR-NEED-001·BR-OBJ-001·BR-OBJ-002·BR-OBJ-003·UN-DATA-001 | AC-DATA-KEY-001 | data quality | Day 1 |
| DR-SCHEMA-001 | Must do | FAQ는 MongoDB support_db.faq, 정형 데이터와 Run·quota·log는 SQL 명세에 따라 저장한다. | BR-NEED-001·UN-SALES-001·UN-FAQ-001 | AC-DATA-SCHEMA-001 | data quality | Day 1 |
| NFR-IDEMP-001 | Must do | 동일 입력을 재실행해도 SQL Row·MongoDB Document가 불필요하게 증가하지 않는다. | BR-OBJ-002·BR-OBJ-004·UN-DATA-001 | AC-IDEMP-001 | pipeline | Day 3 |
| NFR-RETRY-001 | Must do | 재시도 가능한 transport·HTTP 오류만 제한 횟수 내에서 재시도하고 최종 실패를 기록한다. | BR-OBJ-004·UN-OPS-001 | AC-RETRY-001 | pipeline | Day 3 |
| NFR-SOURCE-001 | Must do | route·robots·license·allowlist·403/429·Schema·증분 기준이 불명확하면 우회·write 없이 중단한다. | BR-NEED-001·BR-OBJ-001·BR-OBJ-002·BR-OBJ-004 | AC-SOURCE-001 | collector | Day 2 |
| NFR-SECRET-001 | Must do | credential·API key·DB URI·개인정보를 tracked file·log·Dashboard·Discord에 남기지 않는다. | BR-OBJ-005·BR-OBJ-006·UN-AUD-001 | AC-SECRET-001 | reviewer | Day 3 |
| NFR-OBS-001 | Must do | Run·stage 상태, 단위별 count, sanitized error, Checkpoint를 운영자가 확인할 수 있다. | BR-OBJ-004·BR-OBJ-005·UN-OPS-001·UN-AUD-001 | AC-OBS-001 | pipeline | Day 3 |
| NFR-EXT-001 | Must do | SQL Writer DSN·Business Key·Unique Constraint를 유지하여 Primary–Replica 확장을 가능하게 한다. | BR-NEED-003·BR-OBJ-006 | AC-EXT-001 | data/infra | Day 1 |
| NFR-EXT-002 | Must do | MongoDB faq_id Unique Index·표준 URI를 유지하여 3노드 Replica Set과 과반수 선출로 확장한다. | BR-NEED-003·BR-OBJ-006 | AC-EXT-002 | data/infra | Day 1 |
| NFR-NET-001 | Must do | Backend·SQL·MongoDB를 Private Subnet에 두고 운영자 Public 직접 접근을 차단한다. | BR-NEED-003·BR-OBJ-006·UN-OPS-001 | AC-NET-001 | infra | Day 1 |
| NFR-MVP-001 | Must do | 3일 안에 추가 분산 인프라 없이 세 저장 흐름·운영 Dashboard·Discord·재실행 Evidence를 검증한다. | BR-NEED-002·BR-OBJ-004·UN-OPS-001 | AC-3D-001 | requirements owner | Day 3 |

## 4. Acceptance criteria

| AC ID | Given | When | Then | Evidence | due | evidence_status |
|---|---|---|---|---|---|---|
| AC-ARCH-001 | AWS 권한과 VPC가 준비됨 | MVP 인프라를 확인함 | Bastion·Backend·SQL·MongoDB 4개 호스트와 고정 스택이 확인됨 | evidence/day1-infra.md | Day 1 | planned |
| AC-ACCESS-001 | Backend·DB가 Private Subnet에 있음 | 운영자가 접속함 | 직접 Public 접근은 실패하고 Bastion SSH/Tunnel만 성공함 | evidence/day1-infra.md | Day 1 | planned |
| AC-FAQ-COLLECT-001 | FAQ live Source 또는 versioned fixture가 있음 | 09:00 collector를 실행함 | 허용 범위만 수집되고 차단·Schema 실패 시 write가 없음 | evidence/day2-faq.md | Day 2 | planned |
| AC-FAQ-TRANSFORM-001 | FAQ HTML fixture와 license·attribution metadata가 있음 | transform·validate를 실행함 | identity·content hash·license·attribution을 포함한 FAQ Document와 Reject 원인이 생성됨 | output/<run_id>/faq-quality.json | Day 2 | planned |
| AC-FAQ-LOAD-001 | 유효 FAQ Document가 있음 | 두 번 load하고 답변을 변경함 | 동일 faq_id는 중복되지 않고 변경 내용만 Update됨 | evidence/day2-faq.md | Day 2 | planned |
| AC-LIST-COLLECT-001 | 초기 1만건 listing fixture가 있음 | Worker를 실행함 | 500건씩 최대 20회, 호출 간격 1초 이상, 동시 요청 0건임 | evidence/day2-listing.md | Day 2 | planned |
| AC-LIST-INCREMENT-001 | 마지막 성공 Checkpoint가 C100임 | C101 이후 변경을 실행하고 중간 실패함 | 성공 전 Checkpoint는 C100 유지되고 재실행은 C101 이후부터 시작함 | evidence/listing-checkpoint.md | Day 2 | planned |
| AC-LIST-TRANSFORM-001 | 정상·오류 listing 응답이 있음 | transform·validate를 실행함 | 매물 본체와 5개 참조 엔터티의 ID·SQL 타입이 유효하고 오류 Record는 Reject됨 | output/<run_id>/listing-quality.json | Day 2 | planned |
| AC-LIST-LOAD-001 | 신규·변경·동일 listing이 있음 | 최초 load 후 다시 load함 | 참조 테이블과 매물 본체가 중복 없이 반영되고, 변경은 같은 `listing_id`를 Update하며 동일 입력은 Unchanged가 됨 | evidence/day2-listing.md | Day 2 | planned |
| AC-REG-COLLECT-001 | 실제 API shape fixture와 quota 3,000이 있음 | daily collector를 실행함 | 실행당 API 호출이 1회이고 요청 월의 원천 행이 수집되며 quota 초과가 없음 | evidence/day2-registration.md | Day 2 | planned |
| AC-REG-TRANSFORM-001 | `result_data.formList` 응답이 있음 | transform·validate를 실행함 | 원천 1행의 `승용>관용` 등 모든 지표가 개별 정규화 Row로 분해되고 필수값 Reject가 생성됨 | output/<run_id>/registration-quality.json | Day 2 | planned |
| AC-REG-LOAD-001 | 동일 월·시도명·시군구·차량구분·용도구분 Key가 두 번 있음 | SQL load를 실행함 | Unique 위반이 0건이고 변경 수량만 Update됨 | evidence/day2-registration.md | Day 2 | planned |
| AC-PIPE-STAGE-001 | 세 Pipeline fixture가 있음 | 공통 entry point를 실행함 | Collect·Preprocess·Validate·Load의 상태와 count가 순서대로 기록됨 | evidence/day3-operations.md | Day 2 | planned |
| AC-OPS-LOG-001 | 성공·Reject·실패 Run이 있음 | Log query를 실행함 | run_id·stage·logic·level·count·sanitized error가 확인됨 | evidence/day3-operations.md | Day 3 | planned |
| AC-OPS-DASH-001 | Run·DB·quota 기록이 있음 | Dashboard를 Bastion Tunnel로 엶 | 세 Pipeline·DB 상태·quota·최근 오류가 한 화면에 보임 | evidence/day3-observability.md | Day 3 | planned |
| AC-OPS-DISCORD-001 | Source·DB·Schema 실패 fixture가 있음 | Pipeline을 실행함 | Discord에 민감정보 없는 오류 요약과 notify log가 남음 | evidence/discord-alert.md | Day 3 | planned |
| AC-OPS-SCHEDULE-001 | 수동 성공 Run이 있음 | daily cron과 Worker supervisor를 실행함 | FAQ·등록현황은 1회 scheduled Run, 중고차는 단일 Worker가 실행됨 | evidence/scheduler-run.md | Day 3 | planned |
| AC-OPS-ISOLATE-001 | FAQ 실패·중고차 성공 fixture가 있음 | 두 Pipeline을 함께 실행함 | FAQ는 FAILED, 중고차는 SUCCESS로 독립 기록됨 | evidence/day3-operations.md | Day 3 | planned |
| AC-DATA-KEY-001 | 세 데이터 정상 fixture가 있음 | 저장 후 provenance를 조회함 | Business Key·Source·collected_at·run_id가 모두 역추적됨 | evidence/day1-schema.md | Day 1 | planned |
| AC-DATA-SCHEMA-001 | SQL·MongoDB가 준비됨 | DDL·Index·Collection을 확인함 | 데이터별 저장 위치와 Unique Key가 명세와 일치함 | evidence/day1-schema.md | Day 1 | planned |
| AC-IDEMP-001 | 동일 checksum fixture가 있음 | 같은 입력을 두 번 실행함 | SQL·MongoDB 고유 데이터 수가 불필요하게 증가하지 않음 | evidence/retry-idempotency.md | Day 3 | planned |
| AC-RETRY-001 | timeout·503·비재시도 오류 fixture가 있음 | retry wrapper를 실행함 | 재시도 대상만 설정 횟수 내 재시도하고 최종 상태를 기록함 | evidence/retry-idempotency.md | Day 3 | planned |
| AC-SOURCE-001 | route·robots·403/429·Schema·증분 실패 fixture가 있음 | collector를 실행함 | 우회·DB write 없이 blocked 또는 FAILED와 sanitized 원인이 남음 | evidence/source-guard.md | Day 2 | planned |
| AC-SECRET-001 | 제출 후보·log·Dashboard·Discord payload가 있음 | secret scan을 실행함 | credential·API key·DB URI·개인정보 의심이 0건임 | evidence/requirements-review.md | Day 3 | planned |
| AC-OBS-001 | 성공·실패 Run이 있음 | Dashboard·SQL log를 조회함 | 운영자가 시작·종료·단계·건수·오류·Checkpoint를 확인함 | evidence/observability.md | Day 3 | planned |
| AC-EXT-001 | DDL·Connection URI·Index가 있음 | 확장 검토를 수행함 | SQL Writer/Unique Key와 MongoDB faq_id Index가 확인되고 향후 복제 경계가 명시됨 | evidence/architecture-review.md | Day 1 | planned |
| AC-EXT-002 | MongoDB Collection·Connection URI·Index가 있음 | MongoDB 확장 검토를 수행함 | faq_id Unique Index와 3노드 Replica Set·과반수 선출의 확장 경계가 명시됨 | evidence/architecture-review.md | Day 1 | planned |
| AC-NET-001 | 네 개 AWS 호스트가 있음 | Security Group과 연결을 검사함 | DB·Backend Public inbound가 없고 Bastion 경유가 확인됨 | evidence/day1-infra.md | Day 1 | planned |
| AC-3D-001 | Source route·API key·Discord 설정 또는 fixture가 준비됨 | Day 3 통합 검증을 수행함 | 세 Pipeline·저장·Dashboard·Discord·재실행·검토 Evidence가 모두 planned 또는 pass로 정리됨 | evidence/final-verification.md | Day 3 | planned |

## 5. 의존성·fallback·실패 경계

- Source 정본은 [Source Registry](07_source-registry.md)다.
- Field·Business Key·Index 정본은 [Data Specification](05_Data%20Specification.md)다.
- 서버·네트워크·확장 정본은 [Architecture](06_architecture.md)다.
- live Source가 승인·연결되지 않으면 official-shape/versioned fixture로 Must 요구사항을 재현한다.
- route·robots·license·allowlist·403/429·Schema·증분 기준값 실패는 우회나 write 없이 blocked 또는 FAILED로 기록한다.
- 중고차 요청이 1초보다 오래 걸리면 요청을 겹치지 않고 현재 처리가 끝난 뒤 다음 요청을 시작한다.
- 자동차등록현황보고 quota가 소진되면 추가 API 호출을 하지 않고 다음 실행으로 상태를 남긴다.
- FAILED Run은 마지막 성공 Checkpoint를 전진시키지 않는다.

## 6. Out of scope와 미결 질문

- 영업용 검색·추천·BI·공개 API·고객용 FAQ·AI 응답·계약·결제·CRM·Billing은 제외한다.
- SQL 실제 복제·자동 Failover와 MongoDB 3노드 운영·선출 검증은 제외한다.
- API의 실제 path·field·Pagination·Rate Limit·증분 기준값은 Source Registry 미결 질문으로 관리한다.
- 실제 owner·reviewer·AWS instance size·운영 보존기간은 아직 결정하지 않는다.
- 문서에 구현 완료나 실제 회사 승인을 임의로 표시하지 않는다.

## 7. Review와 baseline

| reviewed_at | reviewer_role | review_result | source_registry_version | note |
|---|---|---|---|---|
| <TODO: ISO-8601> | <TODO> | PENDING | v1 | peer review와 live Source 확인 전 |

source registry, data contract, architecture와 독립 검토가 끝난 뒤에만 document_state를 Baselined로 변경한다.
