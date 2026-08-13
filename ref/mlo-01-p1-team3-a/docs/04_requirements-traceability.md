# Requirements Traceability · BRD→PRD→AC→Evidence

- document_id: RTM-MLO-001
- version: v3
- document_state: Review
- brd_reference: BRD-MLO-001@v3
- prd_reference: PRD-MLO-001@v3
- implementation_reference: docs/00_implementation.md@v5
- source_registry_reference: docs/07_source-registry.md@v2
- data_contract_reference: docs/05_Data Specification.md@v2
- baseline_date: <TODO: YYYY-MM-DD>
- provenance: 사용자 제공 MVP 요구사항과 workshop 기준 문서
- owner_role: <TODO>
- reviewer_roles: [<TODO>]

이 문서는 Business Need → BRD Objective → User Need → PRD Requirement → Acceptance Criteria → Implementation → Test/Evidence를 양방향으로 추적한다. 실제 Issue·PR·실행 결과가 없으므로 implementation과 evidence_status는 planned로 둔다.

## Requirements Traceability Matrix

| business need | BRD objective | user need | PRD requirement | AC | implementation | test/evidence | due | evidence_status |
|---|---|---|---|---|---|---|---|---|
| BR-NEED-003 | BR-OBJ-006 | UN-OPS-001 | FR-ARCH-001 | AC-ARCH-001 | planned feature/<ticket>-aws-mvp | evidence/day1-infra.md | Day 1 | planned |
| BR-NEED-003 | BR-OBJ-006 | UN-OPS-001 | FR-ACCESS-001 | AC-ACCESS-001 | planned feature/<ticket>-bastion-access | evidence/day1-infra.md | Day 1 | planned |
| BR-NEED-001 | BR-OBJ-001 | UN-FAQ-001 | FR-FAQ-COLLECT-001 | AC-FAQ-COLLECT-001 | planned feature/<ticket>-faq-collect | evidence/day2-faq.md | Day 2 | planned |
| BR-NEED-001 | BR-OBJ-001 | UN-FAQ-001 | FR-FAQ-TRANSFORM-001 | AC-FAQ-TRANSFORM-001 | planned feature/<ticket>-faq-transform | output/<run_id>/faq-quality.json | Day 2 | planned |
| BR-NEED-001 | BR-OBJ-001 | UN-FAQ-001 | FR-FAQ-LOAD-001 | AC-FAQ-LOAD-001 | planned feature/<ticket>-faq-load | evidence/day2-faq.md | Day 2 | planned |
| BR-NEED-001 | BR-OBJ-002 | UN-OPS-002 | FR-LIST-COLLECT-001 | AC-LIST-COLLECT-001 | planned feature/<ticket>-listing-worker | evidence/day2-listing.md | Day 2 | planned |
| BR-NEED-001 | BR-OBJ-002 | UN-OPS-002·UN-DATA-001 | FR-LIST-INCREMENT-001 | AC-LIST-INCREMENT-001 | planned feature/<ticket>-listing-checkpoint | evidence/listing-checkpoint.md | Day 2 | planned |
| BR-NEED-001 | BR-OBJ-002 | UN-DATA-001 | FR-LIST-TRANSFORM-001 | AC-LIST-TRANSFORM-001 | planned feature/<ticket>-listing-transform | output/<run_id>/listing-quality.json | Day 2 | planned |
| BR-NEED-001 | BR-OBJ-002 | UN-SALES-001 | FR-LIST-LOAD-001 | AC-LIST-LOAD-001 | planned feature/<ticket>-listing-load | evidence/day2-listing.md | Day 2 | planned |
| BR-NEED-001 | BR-OBJ-003 | UN-SALES-001 | FR-REG-COLLECT-001 | AC-REG-COLLECT-001 | planned feature/<ticket>-registration-collect | evidence/day2-registration.md | Day 2 | planned |
| BR-NEED-001 | BR-OBJ-003 | UN-DATA-001 | FR-REG-TRANSFORM-001 | AC-REG-TRANSFORM-001 | planned feature/<ticket>-registration-transform | output/<run_id>/registration-quality.json | Day 2 | planned |
| BR-NEED-001 | BR-OBJ-003 | UN-SALES-001 | FR-REG-LOAD-001 | AC-REG-LOAD-001 | planned feature/<ticket>-registration-load | evidence/day2-registration.md | Day 2 | planned |
| BR-NEED-002 | BR-OBJ-004 | UN-OPS-001 | FR-PIPE-STAGE-001 | AC-PIPE-STAGE-001 | planned feature/<ticket>-pipeline-stages | evidence/day3-operations.md | Day 2 | planned |
| BR-NEED-002 | BR-OBJ-004 | UN-OPS-001·UN-AUD-001 | FR-OPS-LOG-001 | AC-OPS-LOG-001 | planned feature/<ticket>-logic-logs | evidence/day3-operations.md | Day 3 | planned |
| BR-NEED-002 | BR-OBJ-004 | UN-OPS-001 | FR-OPS-DASH-001 | AC-OPS-DASH-001 | planned feature/<ticket>-ops-dashboard | evidence/day3-observability.md | Day 3 | planned |
| BR-NEED-002 | BR-OBJ-005 | UN-OPS-001·UN-AUD-001 | FR-OPS-DISCORD-001 | AC-OPS-DISCORD-001 | planned feature/<ticket>-discord-alert | evidence/discord-alert.md | Day 3 | planned |
| BR-NEED-002 | BR-OBJ-004 | UN-OPS-001 | FR-OPS-SCHEDULE-001 | AC-OPS-SCHEDULE-001 | planned feature/<ticket>-scheduler-worker | evidence/scheduler-run.md | Day 3 | planned |
| BR-NEED-002 | BR-OBJ-004 | UN-OPS-001 | FR-OPS-ISOLATE-001 | AC-OPS-ISOLATE-001 | planned feature/<ticket>-pipeline-isolation | evidence/day3-operations.md | Day 3 | planned |
| BR-NEED-001 | BR-OBJ-001·BR-OBJ-002·BR-OBJ-003 | UN-DATA-001·UN-AUD-001 | DR-KEY-001 | AC-DATA-KEY-001 | planned feature/<ticket>-data-provenance | evidence/day1-schema.md | Day 1 | planned |
| BR-NEED-001 | BR-OBJ-001·BR-OBJ-002·BR-OBJ-003 | UN-SALES-001·UN-FAQ-001 | DR-SCHEMA-001 | AC-DATA-SCHEMA-001 | planned feature/<ticket>-data-contract | evidence/day1-schema.md | Day 1 | planned |
| BR-NEED-002 | BR-OBJ-004 | UN-DATA-001 | NFR-IDEMP-001 | AC-IDEMP-001 | planned feature/<ticket>-idempotency | evidence/retry-idempotency.md | Day 3 | planned |
| BR-NEED-002 | BR-OBJ-004 | UN-OPS-001 | NFR-RETRY-001 | AC-RETRY-001 | planned feature/<ticket>-retry-policy | evidence/retry-idempotency.md | Day 3 | planned |
| BR-NEED-001·BR-NEED-002 | BR-OBJ-001·BR-OBJ-002·BR-OBJ-004 | UN-OPS-001·UN-AUD-001 | NFR-SOURCE-001 | AC-SOURCE-001 | planned feature/<ticket>-source-guard | evidence/source-guard.md | Day 2 | planned |
| BR-NEED-003 | BR-OBJ-005·BR-OBJ-006 | UN-AUD-001 | NFR-SECRET-001 | AC-SECRET-001 | planned docs/<ticket>-security-review | evidence/requirements-review.md | Day 3 | planned |
| BR-NEED-002 | BR-OBJ-004·BR-OBJ-005 | UN-OPS-001·UN-AUD-001 | NFR-OBS-001 | AC-OBS-001 | planned feature/<ticket>-observability | evidence/observability.md | Day 3 | planned |
| BR-NEED-003 | BR-OBJ-006 | UN-OPS-001 | NFR-EXT-001 | AC-EXT-001 | planned feature/<ticket>-sql-replication-ready | evidence/architecture-review.md | Day 1 | planned |
| BR-NEED-003 | BR-OBJ-006 | UN-OPS-001 | NFR-EXT-002 | AC-EXT-002 | planned feature/<ticket>-mongo-replica-ready | evidence/architecture-review.md | Day 1 | planned |
| BR-NEED-003 | BR-OBJ-006 | UN-OPS-001 | NFR-NET-001 | AC-NET-001 | planned feature/<ticket>-private-network | evidence/day1-infra.md | Day 1 | planned |
| BR-NEED-002 | BR-OBJ-004 | UN-OPS-001 | NFR-MVP-001 | AC-3D-001 | planned docs/<ticket>-final-verification | evidence/final-verification.md | Day 3 | planned |

## Link integrity review

- must_requirement_count: 29
- must_with_ac_count: 29
- orphan_must_requirement_count: 0
- premature_pass_count: 0
- reviewer_role: <TODO>
- reviewed_at: <TODO: ISO-8601>
- link_integrity_review: PENDING

통과 기준은 must_with_ac_count=29, orphan_must_requirement_count=0, premature_pass_count=0이며, 독립 reviewer가 검토한 뒤 link_integrity_review를 PASS로 변경한다.

## Forward / Backward review

### Forward

각 BR-NEED와 BR-OBJ에서 시작하여 UN → PRD → AC → implementation → evidence 연결이 끊기지 않는지 확인한다.

### Backward

각 Evidence에서 어떤 AC·PRD·BRD objective·business need를 검증하는지 확인한다. Evidence가 존재하지만 상위 요구를 설명할 수 없으면 orphan 후보로 표시한다.

## Scope guardrail

다음 기능이 PRD·Issue·Evidence에 등장하면 BRD 변경 검토 없이 구현하지 않는다.

- 사용자용 검색·추천·BI·공개 API
- 고객용 FAQ·AI 자동응답
- SQL 실제 복제·자동 Failover
- MongoDB 3노드 운영·선출 검증
- CAPTCHA·robots·403/429·license 우회
- 개인정보·계약·결제·CRM·Billing

## Change impact

| 변경 대상 | 함께 검토할 영향 |
|---|---|
| FAQ path·selector·identifier | Source Registry, FR-FAQ-*, MongoDB faq_id, AC-FAQ-* |
| 중고차 API·1초 Rate Limit·500건 Batch·증분 기준 | FR-LIST-*, Checkpoint, SQL Upsert, WBS Day 2 |
| 등록현황 일 1회·formList 분해·quota | FR-REG-*, api_quota_usage, 정규화 Row Evidence |
| Business Key·Schema·Index | DR-*, Loader, Idempotency, SQL/MongoDB 확장 |
| AWS route·Security Group·서버 수 | FR-ARCH-*, FR-ACCESS-*, NFR-NET-*, AC-NET-001 |
| Schedule·Worker supervisor | FR-OPS-SCHEDULE-001, pipeline_runs, Dashboard, project plan |

## Review state

현재 문서는 workshop 기준 구조와 요구사항 연결을 반영한 Review 상태다. 실제 Source 계약·인프라·fixture 실행과 peer review가 완료되기 전에는 Baselined 또는 Pass로 표시하지 않는다.
