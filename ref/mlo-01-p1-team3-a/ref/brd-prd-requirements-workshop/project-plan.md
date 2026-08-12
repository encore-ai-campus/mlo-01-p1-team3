# Project plan · 자동차 등록·FAQ 데이터 파이프라인

> starter_id: `encore.chapter1.brd-prd-requirements-workshop.starter`  
> starter_version: `v1`

이 문서는 **누가·언제·어떤 순서로 수행하는가**만 다룬다. 업무 목표·scope는 BRD, 제품 요구·합격 조건은 PRD를 참조하고 본문을 복사하지 않는다.

## 정본 연결

- BRD: `docs/brd.md#BRD-VF-001@v1`
- PRD: `docs/prd.md#PRD-VF-001@v1`
- traceability: `docs/requirements-traceability.md@v1`
- source registry: `config/source-registry.yml@v1`
- data contract: `docs/data-contract.md@v1`
- architecture: `docs/architecture.md@v1`
- requirements change log: `docs/change-log.md`

## 역할

| 역할 | 담당자 또는 team role | 책임 |
|---|---|---|
| requirements owner | `<TODO>` | BRD·PRD·추적표 baseline과 변경 기록 |
| vehicle owner | `<TODO>` | 자동차 collector·transformer·MySQL·quality |
| FAQ owner | `<TODO>` | FAQ collector·transformer·MongoDB·policy |
| pipeline owner | `<TODO>` | entry point·retry·scheduler·log·handoff |
| reviewer | `<TODO>` | diff·AC·evidence·secret·source 경계 검토 |

## 3일 WBS

| 일차 | 작업 | 교육 미션 | PRD 요구 | owner | dependency | 완료 evidence | 상태 |
|---|---|---|---|---|---|---|---|
| Day 21 | BRD·PRD·traceability와 source·schema·infra 기준선 | `REQ-L01`, `REQ-L02`, `REQ-M01`, `REQ-M02`, `REQ-M03` | 해당 없음: 문서 baseline | `<TODO>` | starter v1 | `evidence/requirements-review.md` | planned |
| Day 21 | fixture smoke | `D21-M04` | `FR-RUN-001` | `<TODO>` | schema·repository stub | `evidence/day21-smoke.txt` | planned |
| Day 22 | vehicle 수집·정제·적재·품질 | `D22-M01`, `D22-M02` | `FR-VEH-COLLECT-001`, `FR-VEH-TRANSFORM-001`, `FR-VEH-LOAD-001`, `DR-VEH-001` | `<TODO>` | source registry | `output/<run_id>/quality-report.json` | planned |
| Day 22 | FAQ 제한 수집·정제·적재·조회 | `D22-M03`, `D22-M04` | `FR-FAQ-COLLECT-001`, `FR-FAQ-LOAD-001`, `DR-FAQ-001`, `NFR-SOURCE-001` | `<TODO>` | robots·license·page config | `evidence/day22-evidence.md` | planned |
| Day 23 | retry·멱등성·예약 실행 | `D23-M01`, `D23-M02`, `D23-M03` | `NFR-RETRY-001`, `NFR-IDEMP-001`, `FR-SCHEDULE-001` | `<TODO>` | Day 22 manual success | `evidence/retry-idempotency.md` | planned |
| Day 23 | 최종 query·JSON snapshot·clean clone·cleanup | `D23-M04`, `D23-M05`, `D23-M06` | `FR-QUERY-001`, `NFR-OBS-001`, `NFR-SECRET-001` | `<TODO>` | final fixture target | `evidence/final-verification.md` | planned |

## 일정·담당 변경 기록

| changed_at | WBS row | before | after | reason | owner |
|---|---|---|---|---|---|

일정·담당 변경이 있을 때만 행을 추가한다. 요구 의미가 바뀌면 이 표가 아니라 `docs/change-log.md`에 기록한다.
