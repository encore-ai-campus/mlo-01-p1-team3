# Data Specification — MVP

- document_id: DATA-MLO-001
- version: v2
- document_state: Review
- brd_reference: BRD-MLO-001@v3
- prd_reference: PRD-MLO-001@v3
- source_registry_reference: docs/07_source-registry.md@v2
- baseline_date: <TODO: YYYY-MM-DD>
- provenance: PRD Data Contract와 사용자 저장 요구사항
- owner_role: <TODO>
- reviewer_roles: [<TODO>]

## 1. 문서 목적

본 문서는 수집·전처리·검증이 끝난 데이터를 SQL과 MongoDB에 저장하기 위한 최소 Data Contract를 정의한다. 원본 Source 전체를 별도 Raw DB에 보관하는 범위는 MVP에 포함하지 않는다.

현재 구현 경계는 `src/collection/`, `src/preprocessing/`, `src/loading/`, `src/pipelines/`와 `migrations/`다. DB가 없는 로컬에서는 동일 Business Key를 검증하는 JSONL Sink를 사용하고, 운영 DB에서는 본 문서의 SQL/MongoDB 계약을 사용한다.

정본 관계는 다음과 같다.

- 비즈니스 범위: [BRD](02_Business_Requirements_Document.md)
- 실행 동작: [PRD](03_Product_Requirements_Document.md)
- 필드·Key·Index: 본 문서
- Source·Schedule·Fallback: [Source Registry](07_source-registry.md)
- 서버·접근·복제 확장: [Architecture](06_architecture.md)

## 2. 저장 아키텍처

| 서버 | DB | 저장 데이터 |
|---|---|---|
| `sql-01` | `sales_support_db` | 자동차등록현황보고, 중고차, Pipeline 실행 이력, API quota |
| `sql-01` | `application_logs` | 단계·로직 단위 애플리케이션 로그 |
| `mongo-01` | `support_db` | FAQ 최신 Document |

모든 저장 작업은 Backend에서 수행한다. 운영자는 Bastion을 통해서만 DB에 접근한다.

## 3. 공통 Data Contract

### 3.1 공통 필드

| 필드 | 의미 | 규칙 |
|---|---|---|
| `run_id` | Pipeline 실행 식별자 | 모든 적재·로그에서 추적 가능해야 함 |
| `source_url` 또는 `source_name` | 원본 출처 | 허용된 Source만 기록 |
| `collected_at` | 수집 시각 | UTC 저장 또는 명시된 timezone 저장 |
| `created_at` | 최초 저장 시각 | Upsert 시 유지 |
| `updated_at` | 마지막 변경 시각 | 실제 변경 시 갱신 |
| Business Key | 논리적 동일 데이터 식별자 | Unique Constraint/Index 적용 |

### 3.2 전처리 규칙

- HTML 태그·불필요한 공백·제어문자를 정규화한다.
- 날짜·숫자는 SQL/MongoDB 계약에 맞는 타입으로 변환한다.
- 필수 식별자 또는 필수 내용이 없으면 Reject한다.
- 결측값을 임의로 `0`, 빈 문자열, 임의 상태로 채우지 않는다.
- Source의 원래 상태값을 현재 계약의 표준 enum으로 검증해 `source_status`에 저장한다. 별도 내부 상태 매핑이 추가될 때만 별도 컬럼을 검토한다.
- 동일 데이터 판단에 사용하는 Key는 수집 실행마다 바뀌지 않아야 한다.

## 4. SQL Database

세부 SQL 엔진은 구현 착수 시 확정한다. 아래 DDL은 기존 프로젝트 호환을 위한 MySQL 계열 예시이며, 요구사항의 논리적 Table·Key를 설명하는 기준이다.

### 4.1 Database 생성

```sql
CREATE DATABASE IF NOT EXISTS sales_support_db;
CREATE DATABASE IF NOT EXISTS application_logs;
```

### 4.2 자동차등록현황보고 — `vehicle_registration_reports`

#### Grain과 Key

국토교통부 API의 `result_data.formList` 한 원천 Row에는 `date`, `시도명`, `시군구`와
`승용>관용`처럼 차량구분·용도구분이 결합된 수량 필드가 함께 들어온다. 전처리 단계는
각 결합 필드를 하나의 SQL Row로 분해한다. 따라서 한 API 원천 Row는 현재 계약상 최대
20개의 정규화 Row가 된다.

한 Row는 **월·시도명·시군구·차량구분·용도구분·수량** 하나의 등록현황 값이다.

여기서 “일 단위 수집”은 Pipeline 실행 주기를 의미한다. 현재 API 예제의 `date`가
`YYYYMM`(`202606`)이므로 Source 자체의 데이터 주기는 월별이며, 일별 값으로 임의
확장하거나 생성하지 않는다. DB에는 조회·정렬이 가능한 `2026-06-01`로 저장한다.

```text
(report_month, sido_name, sigungu_name, vehicle_type, usage_type)
```

#### 필드

| 컬럼 | 타입 예시 | Null | 설명 |
|---|---|---:|---|
| `report_id` | BIGINT | N | 내부 식별자 |
| `report_month` | DATE | N | API `date`/`월`; `YYYYMM`을 해당 월 1일로 저장 |
| `sido_name` | VARCHAR(128) | N | API `시도명` |
| `sigungu_name` | VARCHAR(128) | N | API `시군구`; `계`도 원문 그대로 보존 |
| `vehicle_type` | VARCHAR(128) | N | `승용`, `승합`, `화물`, `특수`, `총계` 등 `>` 앞 구분 |
| `usage_type` | VARCHAR(128) | N | `관용`, `자가용`, `영업용`, `계` 등 `>` 뒤 구분 |
| `quantity` | BIGINT | Y | API 수량; `1,000`은 1000, `-`는 NULL |
| `source_name` | VARCHAR(128) | N | Source 이름 |
| `source_url` | VARCHAR(512) | Y | 호출 endpoint 또는 Source URL |
| `run_id` | CHAR(36) | N | 적재 Run |
| `collected_at` | DATETIME | N | 수집 시각 |
| `created_at` | DATETIME | N | 최초 저장 시각 |
| `updated_at` | DATETIME | N | 마지막 갱신 시각 |
| `content_hash` | CHAR(64) | Y | 정규화된 Row 변경 감지용 해시 |

```sql
CREATE TABLE vehicle_registration_reports (
    report_id BIGINT NOT NULL AUTO_INCREMENT,
    report_month DATE NOT NULL,
    sido_name VARCHAR(128) NOT NULL,
    sigungu_name VARCHAR(128) NOT NULL,
    vehicle_type VARCHAR(128) NOT NULL,
    usage_type VARCHAR(128) NOT NULL,
    quantity BIGINT NULL,
    source_name VARCHAR(128) NOT NULL,
    source_url VARCHAR(512) NULL,
    run_id CHAR(36) NOT NULL,
    collected_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    content_hash CHAR(64) NULL,
    PRIMARY KEY (report_id),
    UNIQUE KEY uq_registration_business
        (report_month, sido_name, sigungu_name, vehicle_type, usage_type),
    KEY ix_registration_month_region (report_month, sido_name, sigungu_name),
    KEY ix_registration_measure (vehicle_type, usage_type),
    KEY ix_registration_run (run_id)
);
```

동일 Business Key가 다시 들어오면 `quantity`, Source metadata, `run_id`, `collected_at`,
`updated_at`을 최신 값으로 갱신한다. 정규화 등록현황 구조는 초기 MVP 기준 migration인
`V001__mvp_schema.sql`에 포함한다.

### 4.3 중고차 — 관계형 현재 상태 모델

#### 왜 한 테이블이 아닌가

중고차 API의 한 매물에는 `brand`, `model`, `location`, `dealer`, `businessArea` 객체가 함께 들어온다. 브라우저의 `/api/v1/cars` 조회와 `ref/autodata-api-crawl-2026-08-11T15-53-16-301Z.json` 100건 표본에서 매물은 100개인데 브랜드 12개, 모델 42개, 소재지 44개가 반복됐다. 따라서 이 객체들을 매물 테이블의 문자열·JSON으로 매번 복제하지 않고 참조 테이블로 분리한다.

MVP의 정규화 범위는 반복되는 참조 엔터티까지다. 가격·주행거리·상태·검사정보·트림처럼 매물 한 건에 종속되는 현재 값은 `vehicle_listings`에 둔다. 가격 이력·상태 이력은 별도 요구가 없으므로 MVP에서 만들지 않는다.

#### 관계와 Grain

```text
vehicle_brands (1) ───< vehicle_models (1) ───< vehicle_listings
vehicle_locations (1) ───────────────────────< vehicle_listings
vehicle_dealers (1) ─────────────────────────< vehicle_listings
vehicle_business_areas (1) ──────────────────< vehicle_listings
vehicle_business_areas (parent) ──< vehicle_business_areas (child)
```

| 테이블 | Grain | Primary Key | 역할 |
|---|---|---|---|
| `vehicle_brands` | API 브랜드 1개 | `brand_id` | 제조사 이름·slug·국가 |
| `vehicle_models` | API 모델 1개 | `model_id` | 브랜드 FK, 모델 이름·slug·차체 유형 |
| `vehicle_locations` | API 소재지 1개 | `location_id` | 시도·시군구·slug |
| `vehicle_dealers` | API 딜러 코드 1개 | `dealer_code` | 마스킹 표시명·부서·직급 |
| `vehicle_business_areas` | API 업무영역 1개 | `business_area_id` | 업무영역과 선택적 상위 영역 |
| `vehicle_listings` | 매물 1개의 최신 상태 | `listing_id` | 매물별 가격·상태·차량 사실과 참조 FK |

모든 테이블은 `run_id`, `collected_at`, `created_at`, `updated_at`를 보존한다. Source가 제공한 등록·변경 시각은 `source_created_at`·`source_updated_at`, 증분 이벤트의 `source_event_id`·`source_sequence`는 매물 본체에 저장한다.

#### 전처리 Stage 계약

전처리는 SQL 문장을 만들지 않고 다음 준비 aggregate 한 건을 만든다.

```json
{
  "listing": {"listing_id": "107416", "model_id": 39, "location_id": 40, "dealer_code": "DLR-32c5a92011", "business_area_id": "BIZ_02923"},
  "brand": {"brand_id": 8, "name": "메르세데스-벤츠"},
  "model": {"model_id": 39, "brand_id": 8, "name": "E-클래스", "body_type": "sedan"},
  "location": {"location_id": 40, "province": "전라남도", "city": "여수시"},
  "dealer": {"dealer_code": "DLR-32c5a92011"},
  "business_area": {
    "business_area_id": "BIZ_02923",
    "parent_business_area_id": "BIZ_00034",
    "parent": {"business_area_id": "BIZ_00034", "name": "호남영업 34"}
  }
}
```

중첩 객체가 존재하면 API가 문서화한 안정 ID(`brand.id`, `model.id`, `location.id`, `dealer.code`, `businessArea.id`)가 없을 때 Reject한다. 변경 이벤트가 일부 필드만 보내는 경우 Loader는 기존 non-null 값을 보존한다.

#### SQL 핵심 계약

```sql
CREATE TABLE vehicle_listings (
    listing_id VARCHAR(128) NOT NULL,
    listing_number VARCHAR(128) NULL,
    title VARCHAR(512) NULL,
    description TEXT NULL,
    trim VARCHAR(256) NULL,
    model_id BIGINT NULL,
    location_id BIGINT NULL,
    dealer_code VARCHAR(128) NULL,
    business_area_id VARCHAR(128) NULL,
    model_year SMALLINT NULL,
    first_registration DATE NULL,
    mileage_km BIGINT NULL,
    price_krw DECIMAL(15,0) NULL,
    currency CHAR(3) NULL,
    source_status VARCHAR(64) NULL,
    fuel_type VARCHAR(64) NULL,
    transmission VARCHAR(64) NULL,
    color VARCHAR(64) NULL,
    displacement_cc INT NULL,
    accident_count INT NULL,
    owner_change_count INT NULL,
    inspection_status VARCHAR(128) NULL,
    source_event_id VARCHAR(128) NULL,
    source_sequence BIGINT NULL,
    content_hash CHAR(64) NULL,
    source_url VARCHAR(512) NULL,
    source_created_at DATETIME NULL,
    source_updated_at DATETIME NULL,
    run_id CHAR(36) NOT NULL,
    collected_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (listing_id),
    FOREIGN KEY (model_id) REFERENCES vehicle_models (model_id),
    FOREIGN KEY (location_id) REFERENCES vehicle_locations (location_id),
    FOREIGN KEY (dealer_code) REFERENCES vehicle_dealers (dealer_code),
    FOREIGN KEY (business_area_id) REFERENCES vehicle_business_areas (business_area_id)
);
```

실제 전체 DDL·Index는 초기 기준선인 `migrations/sql/V001__mvp_schema.sql`에 둔다. 참조 테이블을 먼저 Upsert하고 `vehicle_listings`를 같은 transaction에서 Upsert하여 FK와 매물 현재 상태를 함께 반영한다. 브랜드는 `vehicle_models`를 통해 조인하고 업무영역 부모명은 self-join으로 조회한다.

### 4.4 Pipeline 실행 이력 — `pipeline_runs`

```sql
CREATE TABLE pipeline_runs (
    run_id CHAR(36) NOT NULL,
    pipeline_name VARCHAR(64) NOT NULL,
    schedule_name VARCHAR(64) NULL,
    status VARCHAR(16) NOT NULL,
    started_at DATETIME NOT NULL,
    ended_at DATETIME NULL,
    collected_count INT NOT NULL DEFAULT 0,
    preprocessed_count INT NOT NULL DEFAULT 0,
    valid_count INT NOT NULL DEFAULT 0,
    rejected_count INT NOT NULL DEFAULT 0,
    inserted_count INT NOT NULL DEFAULT 0,
    updated_count INT NOT NULL DEFAULT 0,
    unchanged_count INT NOT NULL DEFAULT 0,
    api_calls INT NOT NULL DEFAULT 0,
    progress_key VARCHAR(256) NULL,
    error_code VARCHAR(64) NULL,
    error_message TEXT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (run_id),
    KEY ix_runs_pipeline_status (pipeline_name, status, started_at),
    KEY ix_runs_started (started_at)
);
```

`error_message`는 sanitized 요약만 저장한다. 성공 Run에서 처리 건수가 0이어도 `SUCCESS` 상태를 기록한다. `FAILED` Run의 `progress_key`는 성공 Checkpoint로 사용하지 않는다.

### 4.5 자동차등록현황보고 API quota — `api_quota_usage`

```sql
CREATE TABLE api_quota_usage (
    quota_date DATE NOT NULL,
    api_name VARCHAR(128) NOT NULL,
    quota_limit INT NOT NULL,
    used_count INT NOT NULL DEFAULT 0,
    last_call_at DATETIME NULL,
    quota_status VARCHAR(32) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (quota_date, api_name)
);
```

`used_count`는 API 호출 전에 안전하게 증가시키거나 예약한다. 네트워크 오류와 재시도도 실제 호출이면 사용량에 포함한다. `used_count`가 `quota_limit`에 도달하면 더 이상 요청하지 않는다.

등록현황 Pipeline은 매일 지정 월 또는 KST 현재 월을 1회 수집한다. 로컬 실행의 `REGISTRATION_STATE_PATH`에는 마지막 성공 월·실행 ID·원천 행 수·정규화 Row 수만 보존하며, 과거 월로 이동하는 `next_period` checkpoint는 사용하지 않는다. 실제 SQL 운영 연결에서는 quota는 `api_quota_usage`를 정본으로 사용하고 실행 결과는 `pipeline_runs`에 기록한다.

### 4.6 중고차 증분 Checkpoint

중고차 API의 마지막 성공 증분 기준값은 별도 서버 파일이 아니라 `pipeline_runs.progress_key`에 보존한다.

로컬 fixture 실행은 DB가 없으므로 `usedcar_checkpoint.json`을 임시 fallback으로 사용한다. SQL Sink를 운영에 연결할 때는 `pipeline_runs`의 성공 Checkpoint를 정본으로 전환하고, 파일 Checkpoint를 운영 정본으로 사용하지 않는다.

| 값 | 저장 내용 |
|---|---|
| `pipeline_name` | `used_car` |
| `status` | `SUCCESS`인 Run만 다음 기준값으로 인정 |
| `progress_key` | Source의 `sequence`, `updated_at`, `cursor` 중 계약된 값 |
| `api_calls` | 해당 Run에서 수행한 API 호출 수 |
| `updated_at` | Checkpoint 확정 시각 |

초기 동기화는 500건 단위 Batch로 처리한다. 1만건이면 20회 호출을 순차 수행하고, 호출 간격은 1초로 둔다. 각 Batch의 적재가 성공하기 전에는 `progress_key`를 전진시키지 않는다. Source가 증분 기준값을 제공하지 않으면 전체 매물을 매초 반복 수집하지 않고 `incremental_contract_missing` 오류로 중단한다.

### 4.7 애플리케이션 로그 — `application_logs.application_logs`

```sql
CREATE TABLE application_logs.application_logs (
    log_id BIGINT NOT NULL AUTO_INCREMENT,
    run_id CHAR(36) NULL,
    pipeline_name VARCHAR(64) NULL,
    stage_name VARCHAR(64) NULL,
    logic_name VARCHAR(128) NOT NULL,
    level_name VARCHAR(16) NOT NULL,
    event_name VARCHAR(128) NULL,
    message TEXT NOT NULL,
    record_key VARCHAR(256) NULL,
    error_code VARCHAR(64) NULL,
    metadata_json JSON NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (log_id),
    KEY ix_logs_run (run_id, created_at),
    KEY ix_logs_logic (logic_name, level_name, created_at)
);
```

`metadata_json`에도 API Key·비밀번호·Webhook URL·원본 개인정보를 넣지 않는다. 로그는 최소 다음 Logic Name을 사용한다.

```text
faq.collect
faq.preprocess
faq.validate
faq.load
used_car.collect
used_car.preprocess
used_car.validate
used_car.load
vehicle_registration.collect
vehicle_registration.quota
vehicle_registration.preprocess
vehicle_registration.load
pipeline.lock
pipeline.finalize
discord.notify
```

## 5. MongoDB Database

### 5.1 Database와 Collection

```text
Database: support_db
Collection: faq
```

### 5.2 FAQ Document

```json
{
  "faq_id": "source-or-stable-key",
  "question": "질문",
  "answer": "답변",
  "brand": "브랜드",
  "category": "카테고리",
  "source_url": "https://official.example/faq/example",
  "license": "source-provided-or-policy-value",
  "attribution": "source-provided-or-policy-value",
  "source_updated_at": null,
  "collected_at": "2026-08-11T09:00:00+09:00",
  "run_id": "uuid",
  "content_hash": "normalized-content-hash",
  "is_active": true,
  "created_at": "2026-08-11T09:00:00+09:00",
  "updated_at": "2026-08-11T09:00:00+09:00"
}
```

### 5.3 FAQ Key와 Index

- Source가 제공하는 `faq_id`를 우선 사용한다.
- Source ID가 없으면 `sha256(normalized_source_url + normalized_question)`을 `faq_id`로 사용한다.
- `faq_id`는 Unique Index로 관리한다.
- Source가 제공하는 `license`와 `attribution`을 보존한다. Source 계약상 필수인데 값이 없으면 Reject한다.
- 현재 FAQ Source는 교육용 재작성 snapshot 정책을 제공하므로 `FAQ_LICENSE`·`FAQ_ATTRIBUTION` 환경설정의 정책 값을 Document에 기록한다. 제3자 공식 URL은 출처로만 보존하고 추가 크롤링하지 않는다.
- `content_hash`는 정규화된 질문·답변·분류를 기준으로 계산한다.
- `brand`, `category`, `is_active`는 Dashboard 이후 조회 확장을 고려해 일반 필드로 유지한다.

```javascript
db.faq.createIndex({ faq_id: 1 }, { unique: true });
db.faq.createIndex({ brand: 1, category: 1 });
db.faq.createIndex({ updated_at: -1 });
```

### 5.4 FAQ Upsert 동작

```javascript
db.faq.updateOne(
  { faq_id: document.faq_id },
  {
    $set: {
      question: document.question,
      answer: document.answer,
      brand: document.brand,
      category: document.category,
      source_url: document.source_url,
      source_updated_at: document.source_updated_at,
      collected_at: document.collected_at,
      run_id: document.run_id,
      content_hash: document.content_hash,
      is_active: document.is_active,
      updated_at: document.updated_at
    },
    $setOnInsert: { created_at: document.created_at }
  },
  { upsert: true }
);
```

FAQ의 과거 변경 이력과 별도 Reject Collection은 MVP 필수가 아니다. Reject 수와 원인은 SQL `pipeline_runs`·`application_logs`로 관리한다.

## 6. Pipeline별 저장 규칙

| Pipeline | 입력 | 전처리 결과 | 저장 규칙 |
|---|---|---|---|
| FAQ | HTML/비정형 | FAQ Document | `faq_id` 기준 MongoDB Upsert |
| 중고차 | API JSON/정형 | 관계형 준비 aggregate → 참조 5개 테이블 + `vehicle_listings` | 참조 엔터티 선 Upsert, 이후 `listing_id` 기준 매물 본체 Upsert; 조회가 필요하면 각 FK로 직접 조인 |
| 자동차등록현황보고 | API `formList`/정형 | `vehicle_registration_reports` 정규화 Row | 월·시도명·시군구·차량구분·용도구분 기준 SQL Upsert |

## 7. 확장 고려사항

### 7.1 SQL Primary–Replica

- 모든 쓰기는 논리적 Writer DSN을 사용한다.
- Table의 Business Key와 Unique Constraint를 제거하지 않는다.
- `created_at`, `updated_at`, `run_id`를 유지해 복제 후 적재 추적이 가능해야 한다.
- MVP에서 Replica가 없더라도 읽기·쓰기 코드에 특정 서버 IP를 흩어 쓰지 않는다.

### 7.2 MongoDB 3노드 Replica Set

- `faq_id` Unique Index를 모든 노드에 동일하게 유지한다.
- 표준 MongoDB Driver Connection URI를 환경설정으로 주입한다.
- 향후 `mongo-01`, `mongo-02`, `mongo-03`이 Replica Set Member가 되고 각 노드가 1표를 가진다.
- 3노드 중 2노드 이상이 동의하는 과반수 선출로 Primary를 결정하는 운영을 2단계에서 검증한다.
- MVP의 단일 서버는 3노드 quorum이나 자동 Failover를 보장하지 않는다.

## 8. 데이터 보존과 운영 원칙

- 중고차와 FAQ는 MVP에서 최신 상태만 보존한다.
- 자동차등록현황보고는 API가 제공하는 월별 자료를 `report_month`별 누적 데이터로 보존한다.
- 운영 로그와 실행 이력은 Dashboard가 조회할 수 있도록 SQL에 보존한다. 정확한 보존 기간은 운영 정책에서 확정한다.
- Source에서 한 번 누락된 데이터를 근거 없이 삭제하지 않는다.
- DB 장애로 로그를 SQL에 쓸 수 없는 경우 Backend 파일 로그에 먼저 남기고, 복구 후 재처리 대상이 되도록 오류를 표시한다.
