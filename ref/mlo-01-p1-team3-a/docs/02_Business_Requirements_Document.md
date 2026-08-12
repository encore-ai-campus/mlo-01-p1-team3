# BRD · 중고차 데이터 수집·전처리·운영 MVP

- document_id: BRD-MLO-001
- version: v3
- document_state: Review
- owner_role: <TODO>
- reviewer_roles: [<TODO>]
- baseline_date: <TODO: YYYY-MM-DD>
- provenance: 사용자 제공 MVP 요구사항과 ref/brd-prd-requirements-workshop 문서 기준을 결합했다. Source credential은 기록하지 않으며, 사용자가 고정한 Source 주소만 요구사항으로 보존한다.

## 1. 배경과 현재 문제

중고차 판매 업무에 필요한 FAQ, 중고차 매물, 자동차등록현황보고는 서로 다른 Source와 갱신 주기를 가진다. 사람이 Source를 따로 확인하고 복사·정리하면 어떤 기준으로 수집했는지, 어느 단계에서 실패했는지, 같은 데이터를 다시 처리했을 때 중복이 생겼는지를 일관되게 재현하기 어렵다.

현재 MVP에서 해결해야 하는 문제는 다음과 같다.

- FAQ를 매일 정해진 시각에 수집하고 최신 상태로 유지해야 한다.
- 중고차 API를 1초 단위로 호출하되, 1회 500건 제한과 초기 1만건·증분 기준을 지켜야 한다.
- 자동차등록현황보고는 매일 1회 API를 호출하고, 한 응답의 `formList` 지표를 모두 분해해 저장해야 한다.
- 수집·전처리·검증·적재·알림의 실패 위치를 운영자가 판단할 수 있어야 한다.
- DB와 Backend를 외부에 직접 노출하지 않고 Bastion을 통해 운영해야 한다.

## 2. Business Need

| ID | 업무 필요 |
|---|---|
| BR-NEED-001 | 외부에 분산된 자동차 데이터를 정해진 기준으로 수집·정제·저장하여 업무에서 재사용할 수 있어야 한다. |
| BR-NEED-002 | 실패 지점·최신성·재실행 가능 여부를 운영자가 근거와 함께 판단할 수 있어야 한다. |
| BR-NEED-003 | 3일 MVP의 단일 서버 구성에서 시작하되 SQL 복제와 MongoDB 3노드 Replica Set으로 확장할 설계 경계를 확보해야 한다. |

## 3. 이해관계자와 사용자 필요

### 3.1 이해관계자

| ID | 이해관계자 | 필요한 업무 결과 |
|---|---|---|
| STK-OPS-001 | Pipeline 운영자 | 세 Pipeline의 상태·실패 지점·재실행 기준·API quota를 확인한다. |
| STK-DATA-001 | 데이터/Backend 담당자 | 수집·전처리·검증·적재를 독립적으로 재현하고 로직별 로그를 확인한다. |
| STK-SALES-001 | 영업 담당자 | MVP가 적재한 최신 중고차·등록현황 데이터를 후속 조회 기능에서 활용한다. |
| STK-FAQ-001 | 고객지원 담당자 | MVP가 적재한 최신 FAQ를 후속 지원 기능에서 활용한다. |
| STK-AUD-001 | 검토자 | Source·Key·품질·처리 결과와 변경 이력을 Evidence로 감사한다. |

### 3.2 사용자 필요

| ID | 사용자 | 사용자 필요 |
|---|---|---|
| UN-OPS-001 | 운영자 | 한 번의 실행 결과에서 성공·실패·Skip·재실행 필요 여부를 확인하고 싶다. |
| UN-OPS-002 | 운영자 | 중고차 마지막 성공 Checkpoint와 1초·500건 처리 결과를 확인하고 싶다. |
| UN-DATA-001 | 데이터 담당자 | 동일 입력을 안전하게 재처리하고 Business Key 중복을 검증하고 싶다. |
| UN-SALES-001 | 영업 담당자 | 최신 매물과 자동차등록현황보고의 Source·기준일을 확인하고 싶다. |
| UN-FAQ-001 | 고객지원 담당자 | FAQ 질문·답변·분류·출처의 최신 상태를 확인하고 싶다. |
| UN-AUD-001 | 검토자 | Source·품질·로그·알림에 민감정보가 없는지 Evidence로 확인하고 싶다. |

## 4. 업무 목표와 측정 방법

| ID | 업무 목표 | 측정 방법 |
|---|---|---|
| BR-OBJ-001 | FAQ 사용자가 최신 FAQ와 출처를 활용할 수 있는 기반을 확보한다. | 동일 FAQ fixture 2회 실행 후 MongoDB Unique Key 증가가 0이고 Source·run_id가 추적된다. |
| BR-OBJ-002 | 중고차 매물의 초기 1만건과 이후 변경을 1초·500건·증분 기준으로 반영한다. | 초기 요청이 500건 단위 20회 이하로 순차 처리되고, 이후 마지막 성공 Checkpoint 이후만 요청되며 SQL 중복이 0이다. |
| BR-OBJ-003 | 자동차등록현황보고의 최신 월별 응답을 매일 정규화해 누적한다. | 하루 실행당 API 호출이 1회이고, 응답 원천 행 수와 분해된 SQL Row 수가 로그에 남으며 동일 월 재실행 시 Business Key 중복이 0이다. |
| BR-OBJ-004 | 운영자가 재실행 필요 여부와 실패 지점을 판단한다. | Dashboard와 SQL log에서 Run·stage·logic·건수·sanitized error·Checkpoint가 모두 보인다. |
| BR-OBJ-005 | 이슈를 Backend에서 처리하고 Discord로 전파한다. | 실패 fixture에서 민감정보 없는 Discord 요약 1건과 notify log가 남는다. |
| BR-OBJ-006 | 단일 서버 MVP를 확장 가능한 AWS 경계로 운영한다. | Bastion 경유 접근이 성공하고 Backend·DB Public 직접 접근이 차단되며 SQL/MongoDB 확장 설정 경계가 문서화된다. |

## 5. Business Requirements

| ID | 비즈니스 요구사항 | 우선순위 |
|---|---|---|
| BR-MVP-01 | FAQ를 http://192.168.0.51:4000/에서 크롤링하여 매일 09:00 KST에 처리한다. | Must |
| BR-MVP-02 | 중고차를 같은 Source API에서 1초마다 수집하고 1회 최대 500건 단위로 초기 적재 후 증분 업데이트한다. | Must |
| BR-MVP-03 | 자동차등록현황보고 API를 매일 1회 호출하고 해당 월의 응답을 수집한다. 일일 3,000회 quota는 초과 방지 상한으로만 사용하며 자동 Backfill에 소진하지 않는다. | Must |
| BR-MVP-04 | 모든 데이터는 수집·전처리·검증·적재의 논리적 레이어를 통과한다. | Must |
| BR-MVP-05 | FAQ를 MongoDB Document로 전처리하고 동일 FAQ 기준으로 Upsert한다. | Must |
| BR-MVP-06 | 중고차 API의 매물 본체와 반복 참조 객체(브랜드·모델·소재지·딜러·업무영역)를 관계형 SQL 테이블로 분리하여 적재하고, `listing_id` 기준으로 매물 본체를 최초 Insert 후 Upsert한다. | Must |
| BR-MVP-07 | 자동차등록현황보고의 각 `formList` 행을 월·시도명·시군구·차량구분·용도구분·수량 Row로 분해해 SQL에 적재하고 중복을 방지한다. | Must |
| BR-MVP-08 | Backend의 간단한 Python Dashboard에서 전체 Pipeline 상태를 확인한다. | Must |
| BR-MVP-09 | 수집·전처리·검증·적재 및 주요 로직별 로그를 Backend에서 처리한다. | Must |
| BR-MVP-10 | 이슈 또는 실패가 발생하면 Backend가 Discord로 안전한 요약을 전파한다. | Must |
| BR-MVP-11 | DB와 Backend의 운영자 접근은 Bastion을 경유한다. | Must |
| BR-MVP-12 | AWS MVP는 SQL 1대, MongoDB 1대, Backend 1대, Bastion 1대로 구성한다. | Must |
| BR-MVP-13 | 구현 스택은 Python, Shell Script, SQL, MongoDB, AWS로 고정한다. | Must |
| BR-MVP-14 | SQL은 Primary–Replica(master–slave), MongoDB는 3노드 Replica Set과 투표·선출 구조로 확장 가능해야 한다. | Must |
| BR-MVP-15 | 동일 입력 재실행으로 중복이 생기지 않고 실패 Pipeline을 안전하게 재실행한다. | Must |
| BR-MVP-16 | 중고차 초기 1만건은 500건씩 최대 20회 순차 호출하고 호출 간격을 1초로 유지한다. | Must |

## 6. In Scope

- BR-SCOPE-001: FAQ·중고차·자동차등록현황보고의 Source Registry와 수집 Schedule
- BR-SCOPE-002: Collect → Preprocess → Validate → Load 레이어와 Data Contract
- BR-SCOPE-003: FAQ MongoDB Upsert, 중고차 SQL Insert/증분 Upsert, 등록현황 SQL Upsert
- BR-SCOPE-004: Run·stage·logic 로그, API quota, Python Dashboard, Discord 오류 전파
- BR-SCOPE-005: AWS 4개 호스트, Private DB/Backend, Bastion 경유 운영 접근
- BR-SCOPE-006: Idempotency·Retry·Lock·Checkpoint·Pipeline isolation
- BR-SCOPE-007: SQL Primary–Replica와 MongoDB 3노드 Replica Set 확장 기준선
- BR-SCOPE-008: versioned fixture·clean Evidence·Requirements review

## 7. Out of Scope

- BR-OOS-001: 영업용 검색·추천·BI·시장 분석 화면과 공개 REST API
- BR-OOS-002: 고객용 FAQ 서비스와 AI 자동응답
- BR-OOS-003: SQL 실제 복제·자동 Failover·읽기 분산
- BR-OOS-004: MongoDB 3개 서버 운영·Replica Set 선출 검증·분산 Worker
- BR-OOS-005: Airflow·Kafka·Spark·메시지 큐·대규모 분산 처리
- BR-OOS-006: 계약·결제·금융·보험·CRM·Billing·개인정보 처리
- BR-OOS-007: CAPTCHA·robots·403·429·allowlist·license 우회
- BR-OOS-008: 실제 경영진 승인이나 운영 SLA를 문서에 임의로 기재하는 행위

## 8. 업무 규칙·제약·가정

### 8.1 규칙

- BR-RULE-001: Schedule은 Asia/Seoul(KST)을 기준으로 한다.
- BR-RULE-002: FAQ·중고차는 고정 Base URL과 허용된 Source 범위만 사용한다.
- BR-RULE-003: 중고차는 1초마다 순차 호출하며 1회 최대 500건을 처리한다. 초기 1만건은 20회 기준으로 처리한다.
- BR-RULE-004: 중고차 초기 동기화 후에는 마지막 성공 Checkpoint 이후만 요청한다. Checkpoint는 적재 성공 후 전진한다.
- BR-RULE-005: 자동차등록현황보고는 실행당 논리적 API 호출을 1회로 제한한다. 재시도도 quota에 포함하며 일일 3,000회를 초과하지 않는다.
- BR-RULE-006: 자동차등록현황보고의 `date`/`월`, `시도명`, `시군구`, `차량구분>용도구분` 수량을 모두 보존하고, 각 결합 지표를 개별 SQL Row로 분해한다.
- BR-RULE-007: 필수 식별자·필드·형식이 깨진 Record는 정상 저장과 구분하여 Reject한다.
- BR-RULE-008: Source에서 한 번 보이지 않은 매물·FAQ를 명시적 삭제 신호 없이 삭제하거나 상태 변경하지 않는다.
- BR-RULE-009: 로그·Dashboard·Discord에 API Key·DB 비밀번호·Webhook·개인정보를 기록하지 않는다.
- BR-RULE-010: FAQ Source가 제공하는 license·attribution·content hash를 보존하고, 정책상 필수 metadata가 없으면 저장하지 않는다.

### 8.2 제약

- BR-CON-001: 구현 스택은 Python, Shell Script, SQL, MongoDB, AWS로 제한한다.
- BR-CON-002: MVP 서버는 Bastion 1대, Backend 1대, SQL 1대, MongoDB 1대로 제한한다.
- BR-CON-003: AWS Backend가 192.168.0.51:4000에 도달할 경로가 없으면 live Source 수집을 실행하지 않는다.
- BR-CON-004: 중고차 API의 1초 Rate Limit·500건 Batch·증분 기준값은 Source 계약으로 확인해야 한다.
- BR-CON-005: 운영 DB에 임의의 샘플 데이터를 live 데이터처럼 적재하지 않는다.

### 8.3 가정

- BR-ASM-001: 운영자는 Bastion에 접근할 허용 IP 또는 VPN을 가진다.
- BR-ASM-002: 자동차등록현황보고 API 인증키와 quota 기준시각이 제공된다.
- BR-ASM-003: 중고차 API는 증분 기준값 sequence·updated_at·cursor 중 하나를 제공한다.
- BR-ASM-004: 운영용 Discord Webhook과 Backend egress가 제공된다.
- BR-ASM-005: Source 준비 전에는 official-shape/versioned fixture로 Must 요구사항을 재현할 수 있다.

## 9. 위험·대응·미결 질문

| ID | 발생 조건 | 영향 | 대응 | owner | 상태 |
|---|---|---|---|---|---|
| BR-RISK-001 | AWS에서 Source route가 없음 | FAQ·중고차 live 수집 불가 | Day 1 smoke에서 차단하고 route 제공 전 운영 실행 금지 | infra owner | open |
| BR-RISK-002 | 중고차 1초·500건·증분 계약이 불명확함 | Worker 구현·증분 검증 불가 | Source Registry를 먼저 확정하고 미지원 시 incremental_contract_missing | vehicle owner | open |
| BR-RISK-003 | 등록현황 API key·quota 기준시각 불명확 | 일일 1회 수집·quota 기록 실패 | 인증·quota·응답 지표를 fixture와 함께 검증 | registration owner | open |
| BR-RISK-004 | 1초 처리보다 HTTP·전처리·적재가 오래 걸림 | 요청 중첩·지연 | 단일 Worker·no-overlap·처리 완료 후 다음 요청 | vehicle/pipeline owner | open |
| BR-RISK-005 | Source Schema·robots/license가 변경됨 | 잘못된 적재·정책 위반 | write 없이 FAILED/blocked evidence, 변경 review | source owner | open |
| BR-RISK-006 | Discord 전송이 실패함 | 장애 전파 지연 | SQL/file log와 Dashboard를 기준 상태로 유지 | pipeline owner | open |
| BR-RISK-007 | 3일 안에 HA나 사용자 기능까지 범위가 커짐 | MVP 완료 지연 | BR-OOS와 WBS를 기준으로 scope freeze | requirements owner | open |

| ID | 미결 질문 | 영향 | 대응 | owner | 상태 |
|---|---|---|---|---|---|
| BR-OQ-001 | FAQ 실제 path·selector·Source ID는 무엇인가? | FAQ crawler·Key | Day 1 Source Registry 확인 | FAQ owner | open |
| BR-OQ-002 | 중고차 API의 실제 path·인증·Pagination은 무엇인가? | API Client | Day 1 계약 확인 | vehicle owner | open |
| BR-OQ-003 | 중고차 증분 기준값은 무엇인가? | Checkpoint·증분 | sequence·updated_at·cursor 중 확정 | vehicle owner | open |
| BR-OQ-004 | 등록현황 API의 일일 quota reset 시각과 최신 `date`/월 제공 시점은 무엇인가? | daily period·quota 기록 | 명세의 `formList` 응답과 live 응답 대조 | registration owner | open |
| BR-OQ-005 | SQL 엔진 세부 버전과 AWS instance size는 무엇인가? | DDL·운영 | 구현 전 결정 | infra/data owner | open |

## 10. 검토 기록과 변경 원칙

| reviewed_at | reviewer_role | review_result | note |
|---|---|---|---|
| <TODO: ISO-8601> | <TODO> | PENDING | 구조 검증 전이며 독립 peer review 필요 |

- 모든 Must 요구사항은 PRD catalog·AC·Traceability에 연결한다.
- Evidence 실행 전 상태는 planned이며, 실행 결과 없이 pass로 바꾸지 않는다.
- baseline 뒤 요구 의미 변경은 [change log](09_change-log.md)에만 기록한다.
- 실제 회사 승인이나 운영 SLA를 받지 않았다면 승인 서명을 꾸미지 않는다.
