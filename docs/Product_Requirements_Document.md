# PRD — 중고 자동차 영업·고객지원 데이터 통합 솔루션

## 1. 문서 목적

본 문서는 중고 자동차 영업·고객지원 데이터 통합 솔루션의 MVP가 제공해야 하는 **데이터 수집·정제·검증·적재 기능과 운영 요구사항**을 정의한다.

본 MVP의 제품 범위는 다음 단계까지이다.

```text
Source
  ↓
Collect
  ↓
Clean / Transform
  ↓
Validate
  ↓
Store
  ↓
Run Metadata
```

사용자 조회, 검색 API, 분석 화면, BI Dashboard 등 **저장된 데이터를 소비하는 기능은 MVP 범위에 포함하지 않는다.**

데이터별 상세 컬럼, 데이터 타입, Key, Null 허용 여부 등의 Data Contract는 별도 **ERD 및 데이터 명세서**에서 관리한다.

---

## 2. MVP 범위

### 2.1 포함 범위

MVP는 다음 3개의 독립적인 데이터 Pipeline으로 구성한다.

| Pipeline | Source | 실행 정책 | 저장소 |
|---|---|---|---|
| Vehicle Registration | 자동차 등록 공공데이터 API | 1일 1회, 최신 데이터 우선 + Historical Backfill | MySQL |
| Vehicle Listing | 프로젝트용 통합 사이트 | 5분 주기, 최초 Snapshot + 이후 증분 수집 | MySQL |
| FAQ | 프로젝트용 통합 사이트 | 1일 1회 | MongoDB |

공통적으로 다음 기능을 제공한다.

- Source 데이터 수집
- 데이터 정제 및 형식 변환
- Data Contract 기반 Validation
- 신규 데이터 저장
- 기존 데이터 갱신
- 논리적 중복 방지
- 실패 데이터 분리
- Pipeline 실행 결과 기록
- 실패 후 안전한 재실행
- 동일 Pipeline의 동시 실행 방지

---

### 2.2 제외 범위

다음 기능은 MVP에 포함하지 않는다.

- 영업 담당자용 데이터 조회 기능
- 중고차 조건 검색 기능
- FAQ 검색 기능
- 사용자용 REST API
- 사용자용 Web UI
- BI Dashboard
- Reporting
- 중고차 매물 변경 이력 보관
- FAQ 변경 이력 보관
- 데이터 분석 및 예측
- 차량 추천
- AI 기반 FAQ 응답
- 실제 계약·결제·금융 기능
- Billing 시스템

---

## 3. 데이터 Source 정의

### 3.1 자동차 등록 공공데이터 API

자동차 등록 현황을 제공하는 외부 공공데이터 API를 사용한다.

현재 확인된 Source 특성은 다음과 같다.

| 항목 | 특성 |
|---|---|
| 데이터 범위 | 약 15년 Historical Data |
| 최신 데이터 갱신 | 약 3일 주기 |
| API 일일 호출 한도 | 3,000회 |
| 적재 전략 | 최신 데이터 우선 확보 후 과거 방향 Backfill |

Pipeline은 Source의 데이터 갱신 주기와 별개로 **1일 1회 실행**한다.

신규 데이터가 없는 날에는 API 호출 Budget을 Historical Backfill에 사용한다.

---

### 3.2 프로젝트용 통합 사이트

본 프로젝트를 위해 구축된 하나의 사이트에서 다음 두 데이터 영역을 제공한다.

```text
프로젝트용 통합 사이트
        │
        ├── 중고차 매물
        │
        └── FAQ
```

물리적인 Source는 하나지만 데이터의 갱신 특성과 저장소가 다르므로 수집 Job을 분리한다.

```text
Vehicle Listing Job
FAQ Job
```

---

## 4. 전체 Pipeline 구조

```text
[자동차 등록 공공데이터 API]
             │
             ▼
 Vehicle Registration
             │
       Clean / Validate
             │
             ▼
           MySQL


[프로젝트용 통합 사이트]
        │             │
        ▼             ▼
 Vehicle Listing     FAQ
        │             │
 Clean / Validate  Clean / Validate
        │             │
        ▼             ▼
      MySQL         MongoDB


     [모든 Pipeline]
             │
             ▼
       pipeline_runs
```

각 Pipeline은 독립적으로 실행되며 하나의 Pipeline 장애가 다른 Pipeline의 실행을 차단하지 않아야 한다.

---

## 5. 자동차 등록 Pipeline

### FR-REG-01 — 실행 주기

Vehicle Registration Pipeline은 **1일 1회 실행**한다.

Source의 최신 데이터가 약 3일 주기로 변경되더라도 Historical Backfill이 완료되지 않은 동안에는 매일 실행한다.

---

### FR-REG-02 — 최신 기준일 확인

Pipeline 실행 시 Source에서 제공되는 최신 데이터 기준일과 현재 저장된 최신 기준일을 비교해야 한다.

판단 결과는 다음 두 경우로 구분한다.

```text
Source 최신일 == DB 최신일
→ 신규 최신 데이터 없음

Source 최신일 > DB 최신일
→ 신규 최신 데이터 존재
```

---

### FR-REG-03 — 최초 적재

자동차 등록 데이터가 아직 존재하지 않는 최초 실행에서는 **Source의 최신 기준일부터 적재를 시작**한다.

적재 방향은 최신 데이터에서 과거 데이터 방향으로 진행한다.

```text
최신 기준일
    ↓
이전 기준일
    ↓
이전 기준일
    ↓
   ...
    ↓
과거
```

목적은 15년치 Historical Data 전체 적재를 기다리지 않고 최신 데이터를 우선 확보하는 것이다.

---

### FR-REG-04 — Historical Backfill

Source 최신 기준일과 DB 최신 기준일이 동일한 경우 신규 최신 데이터를 다시 수집하는 대신, **기존 Historical Backfill의 마지막 지점부터 과거 방향으로 수집을 계속한다.**

예:

```text
Source 최신 데이터
2026-08

이미 확보한 과거 데이터
2026-08
   ↓
   ...
2025-01

다음 Backfill
2024-12부터 시작
```

Backfill은 Source의 최초 데이터까지 반복한다.

---

### FR-REG-05 — 신규 최신 데이터 우선 처리

Source 최신 기준일이 기존 DB 최신 기준일보다 새로운 경우 Historical Backfill을 일시적으로 후순위로 변경한다.

먼저 다음 구간을 채운다.

```text
Source 최신일
      ↓
      ↓ 신규 Gap
      ↓
기존 DB 최신일
```

예:

```text
Source 최신일 : 2026-08-12
DB 최신일     : 2026-08-09

우선 처리

2026-08-12
2026-08-11
2026-08-10

→ 기존 2026-08-09와 연결
```

신규 데이터 Gap을 모두 적재한 이후 API 호출 Budget이 남아 있으면 Historical Backfill을 다시 진행한다.

---

### FR-REG-06 — API 호출 Budget

Pipeline은 Source에서 허용하는 **일일 최대 3,000회 API 호출 제한을 초과하지 않아야 한다.**

최신일 확인, 데이터 조회, Pagination 등 Source API에 대한 모든 호출은 동일한 일일 Budget에 포함하여 관리한다.

처리 우선순위는 다음과 같다.

```text
1. 최신 데이터 여부 확인
        ↓
2. 신규 최신 데이터 Gap 적재
        ↓
3. 남은 Budget 계산
        ↓
4. Historical Backfill
```

신규 Gap 적재만으로 당일 Budget이 소진되면 Historical Backfill은 다음 실행으로 이월한다.

---

### FR-REG-07 — Historical Backfill 완료

Source가 보유한 가장 오래된 기준일까지 정상 적재된 경우 Historical Backfill을 완료 상태로 판단한다.

그 이후 Pipeline은 신규 최신 데이터 존재 여부 확인과 신규 데이터 적재만 수행한다.

```text
Backfill 완료 이후

최신 데이터 확인
      ↓
신규 데이터?
  ┌───┴───┐
 Yes      No
  │        │
적재      종료
```

---

### FR-REG-08 — 중복 방지

동일한 자동차 등록 데이터가 재수집되더라도 논리적으로 동일한 레코드가 중복 생성되지 않아야 한다.

구체적인 Business Key와 Unique Constraint는 ERD에서 정의한다.

PRD에서는 다음 동작만 보장한다.

```text
신규 레코드
→ INSERT

기존 레코드
→ UPDATE 또는 유지

동일 데이터 재처리
→ 중복 Row 생성 금지
```

---

## 6. 중고차 매물 Pipeline

### FR-LST-01 — 실행 주기

Vehicle Listing Pipeline은 **5분마다 실행**한다.

---

### FR-LST-02 — 최초 Snapshot

최초 실행에서는 현재 Source에 존재하는 전체 매물 Snapshot을 수집해야 한다.

Source에서 제공하는 Cursor 기반 수집 방식을 이용하여 전체 데이터의 끝까지 처리한다.

```text
Initial Run
    ↓
Snapshot 시작
    ↓
Cursor 단위 수집
    ↓
Clean
    ↓
Validate
    ↓
Upsert
    ↓
다음 Cursor
    ↓
전체 Snapshot 완료
```

초기 Snapshot이 정상 완료된 시점의 변경 Sequence를 이후 증분 수집의 시작점으로 사용한다.

---

## 7. 중고차 증분 수집

### FR-LST-03 — Sequence 기반 증분 수집

초기 Snapshot 완료 후에는 전체 매물을 다시 수집하지 않는다.

마지막 정상 실행에서 처리한 Sequence 이후의 변경 데이터만 수집한다.

```text
Last Successful Sequence
          ↓
   Changes after Sequence
          ↓
    신규 / 변경 데이터
          ↓
        Validate
          ↓
         Upsert
```

---

### FR-LST-04 — Checkpoint

증분 수집의 Checkpoint는 **정상적으로 완료된 Pipeline의 Sequence만 인정**한다.

Pipeline 도중 실패한 경우 해당 Run에서 확인한 최신 Sequence를 다음 실행 시작점으로 사용해서는 안 된다.

```text
마지막 SUCCESS
sequence = 1000

다음 Run
1001 ~ 1100 처리
       ↓
처리 중 FAILED

checkpoint
1000 유지
```

다음 실행은 다시 `1000` 이후부터 처리한다.

---

## 8. 중고차 Upsert

### FR-LST-05 — 동일 매물 식별

동일한 중고차 매물은 Source에서 제공하는 안정적인 식별자를 기준으로 판단한다.

현재 초안 기준 Business Identifier는:

```text
listing_number
```

이다.

DB의 실제 PK/UK 구성은 ERD에서 확정한다.

---

### FR-LST-06 — Upsert 처리

매물 처리 결과는 다음 네 가지로 구분한다.

| 결과 | 조건 | 처리 |
|---|---|---|
| INSERTED | 기존에 없는 매물 | 신규 저장 |
| UPDATED | 기존 매물의 관리 대상 값 변경 | 기존 데이터 갱신 |
| UNCHANGED | 기존 데이터와 동일 | 저장 데이터 유지 |
| REJECTED | Validation 실패 | 정상 데이터에 반영하지 않음 |

---

### FR-LST-07 — 최신 상태 유지

중고차 매물은 **현재 최신 상태만 저장한다.**

예:

```text
기존
listing_number = UC-00104924
status = AVAILABLE
price = 35,000,000
```

다음 수집:

```text
listing_number = UC-00104924
status = RESERVED
price = 34,000,000
```

저장 결과:

```text
listing_number = UC-00104924
status = RESERVED
price = 34,000,000
```

과거 값은 별도의 History Row로 보관하지 않는다.

---

### FR-LST-08 — 상태 변경

매물의 판매 상태는 Source에서 전달하는 상태를 기준으로 갱신한다.

Source가 명시적인 상태 변경을 제공한 경우 현재 저장된 상태를 최신 상태로 갱신해야 한다.

---

### FR-LST-09 — 미수집 매물

기존에 존재하던 매물이 한 번의 수집 결과에서 발견되지 않았다는 이유만으로 임의의 상태 변경을 수행하지 않는다.

```text
이전 실행
UC-00104924 존재

현재 실행
UC-00104924 미수집
```

위 상황만으로 `SOLD` 등의 상태로 변경하지 않는다.

상태 변경 또는 삭제 여부는 Source가 명시적으로 제공하는 정보를 기준으로 처리한다.

---

## 9. FAQ Pipeline

### FR-FAQ-01 — 실행 주기

FAQ Pipeline은 **1일 1회 실행**한다.

Vehicle Listing Pipeline과 독립적으로 수행한다.

---

### FR-FAQ-02 — 데이터 수집

프로젝트용 통합 사이트의 FAQ 데이터를 수집하여 다음 흐름으로 처리한다.

```text
Collect
   ↓
Clean
   ↓
Validate
   ↓
MongoDB Upsert
```

---

### FR-FAQ-03 — 동일 FAQ 식별

동일 FAQ 판단은 Source에서 제공하는 안정적인 FAQ 식별자를 사용한다.

현재 기준은:

```text
faq_id
```

이다.

구체적인 Index와 Document Schema는 데이터 명세에서 확정한다.

---

### FR-FAQ-04 — FAQ Upsert

FAQ 처리 결과는 다음과 같다.

| 상태 | 처리 |
|---|---|
| 신규 FAQ | INSERT |
| 기존 FAQ + 내용 변경 | UPDATE |
| 기존 FAQ + 동일 | UNCHANGED |
| Validation 실패 | REJECTED |

---

### FR-FAQ-05 — 최신 상태 유지

FAQ도 매물 데이터와 동일하게 별도의 변경 이력을 저장하지 않는다.

기존 FAQ가 변경되면 현재 Document를 갱신한다.

---

### FR-FAQ-06 — 미수집 FAQ

FAQ가 단일 실행에서 발견되지 않았다는 이유만으로 즉시 삭제하지 않는다.

Source에서 명시적인 삭제 또는 상태 변경 정보가 제공되는 경우에만 해당 변경을 반영한다.

---

## 10. Validation

### FR-COM-01 — Data Contract 적용

각 Pipeline은 저장 전에 데이터가 별도 Data Contract를 만족하는지 검증해야 한다.

PRD에서는 상세 컬럼별 Rule을 고정하지 않는다.

Data Contract는 ERD 및 데이터 명세서에서 관리하며 Pipeline은 해당 명세를 기준으로 Validation을 수행한다.

Validation 대상에는 최소 다음 범주가 포함된다.

- 식별 가능 여부
- 필수 데이터 존재 여부
- 데이터 형식
- 데이터 타입 변환 가능 여부
- 허용 값 여부
- 중복 식별 가능 여부

---

## 11. Record Error 처리

### FR-COM-02 — Record 단위 Reject

일부 레코드의 Validation 실패가 전체 Pipeline 실패로 이어져서는 안 된다.

예:

```text
Collected : 1,000
Valid     :   980
Rejected  :    20
```

정상 980건은 계속 적재하며 20건은 `REJECTED`로 집계한다.

Reject 상세 원인은 운영 로그를 통해 확인 가능해야 한다.

MVP에서는 별도의 Reject 전용 DB 테이블을 필수로 하지 않는다.

---

### FR-COM-03 — 전체 Validation 이상

Source에서 데이터가 정상적으로 반환되었으나 수집 레코드 전체 또는 비정상적으로 많은 데이터가 Data Contract를 만족하지 못하여 정상적인 처리가 불가능한 경우 단순 Record Error가 아닌 Pipeline Error로 판단할 수 있어야 한다.

구체적인 임계 기준은 데이터 명세 및 테스트 과정에서 확정한다.

---

## 12. Pipeline 실행 상태

### FR-COM-04 — 실행 상태

Pipeline 실행 상태는 최소 다음 상태를 구분할 수 있어야 한다.

```text
RUNNING
SUCCESS
FAILED
SKIPPED
```

`SKIPPED`는 동일 Pipeline의 이전 실행이 아직 진행 중인 상황에서 새로운 스케줄 실행을 수행하지 않은 경우 사용한다.

---

### FR-COM-05 — SUCCESS

다음 조건을 만족하면 Pipeline을 `SUCCESS`로 처리한다.

- Source 접근이 정상적으로 완료됨
- 해당 실행 범위의 수집이 완료됨
- 정상 레코드 저장이 완료됨
- 필요한 Checkpoint가 정상 확정됨
- 일부 Record Error는 허용됨

변경 데이터가 없어 처리 건수가 0건인 경우도 정상 실행이면 `SUCCESS`이다.

---

### FR-COM-06 — FAILED

다음 상황은 Pipeline 실패로 판단한다.

- Source 연결 실패
- Source 데이터를 정상적으로 읽을 수 없음
- DB 연결 실패
- 정상 레코드 저장 실패
- Checkpoint를 안전하게 확정할 수 없음
- Source Schema 이상 등으로 정상 처리 자체가 불가능함

`FAILED` Run은 새로운 Checkpoint를 확정해서는 안 된다.

---

## 13. 재처리 정책

### FR-COM-07 — At-least-once Processing

Pipeline 장애가 발생한 경우 마지막 정상 처리 지점 이후의 데이터를 다시 처리한다.

이 과정에서 일부 데이터가 반복 처리될 수 있다.

따라서 Pipeline은 다음 조합으로 재처리 안전성을 확보한다.

```text
At-least-once Collection
          +
Idempotent Upsert
```

동일 데이터가 재처리되어도 논리적 중복이 생성되지 않아야 한다.

---

## 14. 동시 실행 정책

### FR-COM-08 — 동일 Pipeline 중복 실행 금지

동일한 Pipeline의 복수 Instance가 동시에 실행되어서는 안 된다.

예:

```text
15:00 Vehicle Listing
        │
        └──── 실행 중

15:05 Vehicle Listing
        ↓
      SKIPPED
```

MVP에서는 이전 실행이 완료되지 않았다면 다음 스케줄 실행을 Skip하는 것을 기본 정책으로 한다.

Lock 구현 방식은 기술 설계 단계에서 결정한다.

---

## 15. Pipeline 실행 이력

### FR-COM-09 — Run Metadata

모든 Pipeline 실행은 `pipeline_runs`를 통해 실행 결과를 기록해야 한다.

구체적인 테이블 컬럼은 ERD에서 정의하되 논리적으로 최소 다음 정보를 보존해야 한다.

| 구분 | 필요한 정보 |
|---|---|
| 실행 식별 | Run ID, Pipeline 종류 |
| 실행 시간 | 시작 시각, 종료 시각 |
| 상태 | RUNNING / SUCCESS / FAILED / SKIPPED |
| 수집 결과 | 수집 건수 |
| 저장 결과 | INSERTED / UPDATED / UNCHANGED |
| 품질 결과 | REJECTED 건수 |
| 진행 상태 | Sequence, Cursor 또는 Backfill 위치 |
| 장애 정보 | 실패 원인 요약 |

---

## 16. Checkpoint 관리

### FR-COM-10 — Checkpoint 원칙

Checkpoint가 필요한 Pipeline은 **마지막 성공 실행의 처리 위치**만 다음 실행의 기준으로 사용한다.

실행 중 확인한 Cursor 또는 Sequence를 데이터 저장 완료 전에 확정해서는 안 된다.

```text
Collect
   ↓
Validate
   ↓
Store
   ↓
필수 처리 완료
   ↓
SUCCESS
   ↓
Checkpoint 확정
```

---

## 17. 저장 책임

본 PRD에서는 테이블의 세부 스키마를 정의하지 않고 각 저장 객체의 책임만 정의한다.

### 17.1 MySQL

#### Vehicle Registration Data

자동차 등록 공공데이터의 정제·검증된 결과를 저장한다.

정확한 Table 및 Key 구조는 ERD에서 정의한다.

#### `vehicle_listings`

중고차 매물의 **현재 최신 상태**를 저장한다.

```text
1 listing
=
1 current state
```

매물의 과거 상태를 별도로 저장하지 않는다.

#### `pipeline_runs`

모든 데이터 Pipeline의 실행 이력과 처리 결과를 저장한다.

별도의 Checkpoint Table을 MVP 필수사항으로 두지 않는다.

---

### 17.2 MongoDB

FAQ의 현재 최신 상태를 Document 형태로 저장한다.

동일 `faq_id`에 대한 변경 이력을 별도 Document로 누적하지 않는다.

---

## 18. 스케줄 정책

| Pipeline | 실행 주기 | 처리 방식 |
|---|---|---|
| Vehicle Registration | 매일 1회 | Freshness 우선 + Historical Backfill |
| Vehicle Listing | 5분마다 | Initial Snapshot + Incremental |
| FAQ | 매일 1회 | Upsert |

Scheduler의 구체적인 구현 기술은 PRD에서 고정하지 않는다.

---

## 19. 아키텍처 제약사항

첨부된 AWS 아키텍처를 제품 실행 환경의 기준으로 사용한다.

PRD에서는 구체적인 IP·CIDR·설정 명령을 정의하지 않고 다음 제약조건만 적용한다.

### NFR-01 — Collector 격리

Collector / ETL Server는 Private Network 영역에서 실행한다.

외부 Source 접근은 NAT Gateway를 통해 이루어진다.

---

### NFR-02 — DB 비공개

MySQL과 MongoDB는 Internet에서 직접 접근할 수 없어야 한다.

Public IP를 통한 DB 직접 접근은 허용하지 않는다.

---

### NFR-03 — 관리 접근

Private Network 내부 서버의 관리 접근은 Bastion Host를 경유한다.

---

### NFR-04 — MySQL 복제

MySQL Primary의 데이터를 Secondary에 복제할 수 있는 구조를 유지한다.

MVP에서 자동 Failover는 필수 요구사항으로 하지 않는다.

---

### NFR-05 — MongoDB Replica Set

MongoDB는 복수 Node Replica Set 구조를 사용하여 데이터 복제를 수행한다.

---

## 20. 비기능 요구사항

### NFR-06 — Idempotency

동일 데이터 또는 동일 처리 구간을 반복 수행해도 논리적 중복이 발생하지 않아야 한다.

---

### NFR-07 — Recoverability

Pipeline 실패 이후 마지막 정상 처리 지점부터 재처리할 수 있어야 한다.

---

### NFR-08 — Pipeline Isolation

Vehicle Registration, Vehicle Listing, FAQ Pipeline은 독립적으로 실행되어야 한다.

하나의 Pipeline 실패가 다른 Pipeline 실행을 차단하지 않아야 한다.

---

### NFR-09 — Observability

운영자는 로그 및 `pipeline_runs`를 통해 최소 다음 질문에 답할 수 있어야 한다.

```text
어떤 Pipeline이 실행되었는가?
언제 시작하고 종료되었는가?
성공했는가?
몇 건을 수집했는가?
몇 건을 신규 저장했는가?
몇 건을 갱신했는가?
몇 건을 Reject했는가?
어디까지 정상 처리했는가?
실패했다면 왜 실패했는가?
```

별도의 운영 Dashboard는 MVP 필수 요구사항으로 하지 않는다.

---

### NFR-10 — Credential Security

API 인증정보, DB 계정 및 비밀번호 등의 Secret은 Source Code에 직접 포함하지 않는다.

Secret 값은 로그에도 출력하지 않는다.

---

### NFR-11 — API Quota Compliance

자동차 등록 공공데이터 Pipeline은 일일 API 호출 한도를 초과하지 않아야 한다.

---

## 21. Acceptance Criteria

### AC-REG — 자동차 등록 Pipeline

다음 시나리오가 정상 동작해야 한다.

**Scenario A — 최초 적재**

```text
DB 비어 있음
→ Source 최신 기준일 확인
→ 최신 데이터부터 적재
→ 남은 API Budget으로 과거 방향 Backfill
```

**Scenario B — 신규 데이터 없음**

```text
Source 최신일 == DB 최신일
→ 신규 데이터 수집 생략
→ 기존 Backfill 위치부터 과거 데이터 추가
```

**Scenario C — 신규 데이터 존재**

```text
Source 최신일 > DB 최신일
→ 새로운 기간 우선 적재
→ 기존 최신 데이터까지 Gap 연결
→ 남은 Budget으로 Historical Backfill
```

**Scenario D — API Budget 부족**

```text
신규 Gap 처리 중
→ 일일 API Budget 소진
→ Backfill 수행하지 않음
→ 다음 실행에서 신규 Gap 우선 재개
```

**Scenario E — 중복 재처리**

동일 기간을 다시 처리해도 동일 논리 레코드가 중복 생성되지 않아야 한다.

---

### AC-LST — 중고차 Pipeline

**Scenario A — Initial Snapshot**

전체 Snapshot이 끝까지 적재되고 이후 증분 수집에 사용할 Sequence를 정상 확정할 수 있어야 한다.

**Scenario B — 신규 매물**

```text
Source: 신규 listing_number
→ INSERTED
```

**Scenario C — 기존 매물 변경**

```text
기존 매물의 status / price 등 변경
→ UPDATED
→ 기존 Row가 최신 상태로 변경
```

**Scenario D — 변경 없음**

```text
기존 매물 + 값 동일
→ UNCHANGED
→ 중복 Row 없음
```

**Scenario E — Pipeline 실패**

```text
마지막 SUCCESS sequence = 1000
1001~1100 처리 중 실패
→ FAILED
→ checkpoint = 1000 유지
```

**Scenario F — 재실행**

마지막 정상 Sequence 이후를 다시 처리하더라도 Upsert로 인해 중복 Row가 생성되지 않아야 한다.

**Scenario G — 미수집**

매물이 한 번의 수집에서 보이지 않았다는 이유만으로 임의로 `SOLD` 처리되지 않아야 한다.

---

### AC-FAQ — FAQ Pipeline

- 1일 1회 실행 가능
- 신규 FAQ 저장 가능
- 기존 FAQ 변경 시 최신 Document 갱신
- 동일 FAQ 중복 생성 방지
- 일부 Reject 발생 시 정상 FAQ 계속 처리
- 단일 실행에서 미수집되었다는 이유만으로 임의 삭제하지 않음

---

### AC-COM — 공통 운영

- 모든 Run의 시작과 종료 상태를 기록할 수 있다.
- `SUCCESS`, `FAILED`, `SKIPPED`를 구분할 수 있다.
- 처리 건수를 확인할 수 있다.
- Reject 건수를 확인할 수 있다.
- 실패 원인을 확인할 수 있다.
- FAILED Run이 Checkpoint를 전진시키지 않는다.
- 동일 Pipeline이 중복 실행되지 않는다.
- 한 Pipeline의 실패가 다른 Pipeline을 중단시키지 않는다.

---

## 22. 별도 산출물과의 경계

PRD에서 다음 사항은 확정하지 않는다.

| 사항 | 관리 문서 |
|---|---|
| 정확한 Table / Collection 구조 | ERD |
| 컬럼·필드 목록 | 데이터 명세서 |
| 데이터 타입 | 데이터 명세서 / ERD |
| PK / UK / 복합 Business Key | ERD |
| 세부 Validation Rule | 데이터 명세서 |
| DB Index | DB 설계 |
| 실제 Upsert SQL | 구현 |
| Python Module/Class 구조 | 기술 설계 |
| Scheduler 구현 방식 | 기술 설계 |
| Lock 구현 방식 | 기술 설계 |
| Retry 횟수와 Backoff | 기술/운영 설계 |
| CIDR/IP/상세 Security Group | 인프라 설계 |
| 솔루션 공급 금액 | BRD / 비용 산출서 |
| 유지보수 금액 | BRD / 비용 산출서 |

이 경계를 두는 게 중요합니다. **PRD는 Data Contract나 구현 코드를 대신하는 문서가 아닙니다.**

---

## 23. TBD

초안 단계에서 다음 내용은 변경 가능 항목으로 유지한다.

| ID | 항목 |
|---|---|
| TBD-01 | 자동차 등록 공공데이터의 정확한 Business Key |
| TBD-02 | 자동차 등록 API Cursor/Pagination 세부 처리 |
| TBD-03 | Source별 상세 Data Contract |
| TBD-04 | 중고차 상태 Enum 및 변경 가능 필드 |
| TBD-05 | Source의 명시적 삭제 이벤트 처리 방식 |
| TBD-06 | FAQ 상세 Data Contract |
| TBD-07 | Validation 세부 Rule |
| TBD-08 | Pipeline Retry 정책 |
| TBD-09 | Scheduler 구현 기술 |
| TBD-10 | Lock 구현 기술 |
| TBD-11 | 로그 보존 정책 |
| TBD-12 | MySQL 장애 전환 운영 절차 |

---

## 24. PRD 요구사항 ID 기준

초안이 계속 변경될 가능성이 높으므로 기능 영역별 Prefix를 사용한다.

| Prefix | 의미 |
|---|---|
| `FR-REG-XX` | 자동차 등록 Pipeline |
| `FR-LST-XX` | 중고차 매물 Pipeline |
| `FR-FAQ-XX` | FAQ Pipeline |
| `FR-COM-XX` | 공통 Pipeline 기능 |
| `NFR-XX` | 비기능 요구사항 |
| `AC-XXX` | Acceptance Criteria |
| `TBD-XX` | 미확정 사항 |

삭제된 ID는 새로운 요구사항에 재사용하지 않는다.