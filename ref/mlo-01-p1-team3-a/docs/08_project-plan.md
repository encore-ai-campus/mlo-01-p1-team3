# Project Plan — 3일 MVP

이 문서는 누가·언제·어떤 순서로 수행하는지만 관리한다. 업무 목표는 BRD, 제품 요구와 Acceptance는 PRD, 필드·Key는 데이터 명세를 정본으로 한다.

## 1. 정본 연결

- Implementation Plan: [00_implementation.md](00_implementation.md)
- BRD: [02_Business_Requirements_Document.md](02_Business_Requirements_Document.md)
- PRD: [03_Product_Requirements_Document.md](03_Product_Requirements_Document.md)
- Traceability: [04_requirements-traceability.md](04_requirements-traceability.md)
- Architecture: [06_architecture.md](06_architecture.md)
- Source Registry: [07_source-registry.md](07_source-registry.md)
- Data Contract: [05_Data Specification.md](05_Data%20Specification.md)
- Change Log: [09_change-log.md](09_change-log.md)
- Review Evidence: [10_requirements-review.md](10_requirements-review.md)

## 2. 역할

| 역할 | 담당자 | 책임 |
|---|---|---|
| requirements owner | <TODO> | BRD·PRD·추적표 기준선과 변경 기록 |
| infra owner | <TODO> | AWS 4개 호스트·Bastion·Network route |
| vehicle owner | <TODO> | 중고차 Worker·Batch·증분·SQL Upsert |
| FAQ owner | <TODO> | FAQ crawler·전처리·MongoDB |
| registration owner | <TODO> | 등록현황 일 1회·formList 분해·3,000 quota 보호·SQL Upsert |
| pipeline owner | <TODO> | 단계·retry·lock·log·Dashboard·Discord |
| reviewer | <TODO> | 요구사항·AC·evidence·secret·source 경계 검토 |

## 3. 3일 WBS

| 일차 | 작업 | PRD 요구 | owner | dependency | 완료 Evidence | 상태 |
|---|---|---|---|---|---|---|
| Day 1 | BRD·PRD·Source Registry·Architecture·Traceability review | 문서 전체 | <TODO> | 사용자 요구사항 | evidence/day1-requirements.md | planned |
| Day 1 | AWS 4개 호스트·Bastion·Source route smoke | FR-ARCH-001, FR-ACCESS-001, NFR-NET-001 | <TODO> | AWS access | evidence/day1-infra.md | planned |
| Day 1 | SQL/MongoDB Data Contract·Key·Index | DR-KEY-001, DR-SCHEMA-001 | <TODO> | Source field 확인 | evidence/day1-schema.md | planned |
| Day 2 | FAQ 수집·전처리·MongoDB Upsert | FR-FAQ-COLLECT-001, FR-FAQ-TRANSFORM-001, FR-FAQ-LOAD-001 | <TODO> | FAQ Source/fixture | evidence/day2-faq.md | planned |
| Day 2 | 중고차 1초 Worker·500건 Batch·초기 1만건·증분·관계형 참조 적재 | FR-LIST-COLLECT-001, FR-LIST-INCREMENT-001, FR-LIST-TRANSFORM-001, FR-LIST-LOAD-001 | <TODO> | API 계약 | evidence/day2-listing.md | planned |
| Day 2 | 자동차등록현황보고 일 1회·formList 지표 분해·3,000 quota 보호·SQL Upsert | FR-REG-COLLECT-001, FR-REG-TRANSFORM-001, FR-REG-LOAD-001 | <TODO> | API key/fixture | evidence/day2-registration.md | planned |
| Day 3 | 공통 Run·stage log·retry·idempotency·isolation | FR-PIPE-STAGE-001, FR-OPS-LOG-001, NFR-IDEMP-001, NFR-RETRY-001 | <TODO> | Day 2 manual success | evidence/day3-operations.md | planned |
| Day 3 | Python Dashboard·Discord·Shell/cron/Worker supervisor | FR-OPS-DASH-001, FR-OPS-DISCORD-001, FR-OPS-SCHEDULE-001 | <TODO> | Run metadata/log | evidence/day3-observability.md | planned |
| Day 3 | 최종 AC·secret·source guard·clean clone review | 전체 AC | <TODO> | 모든 fixture | evidence/final-verification.md | planned |

## 4. 일정·담당 변경 기록

| changed_at | WBS row | before | after | reason | owner |
|---|---|---|---|---|---|
| <TODO> | <TODO> | <TODO> | <TODO> | <TODO> | <TODO> |

요구 의미가 바뀌면 일정표가 아니라 [change log](09_change-log.md)에 기록한다.
