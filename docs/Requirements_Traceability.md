# Requirements Traceability · 중고 자동차 영업·고객지원 데이터 통합 솔루션

> document_id: `RTM-MLO-01-03-001`  
> version: `v0.1`  
> document_state: `Draft`  
> project: `중고 자동차 영업·고객지원 데이터 통합 솔루션`  
> team: `MLO-01-03`  
> brd_reference: `Business_Requirements_Document.md` (current baseline)  
> prd_reference: `TBD - PRD baseline 후 확정`  
> change_log: `Change_Log.md` (추가 예정)  
> review_evidence: `Requirements_Review_Evidence.md` (추가 예정)

---

## 1. 문서 목적

이 문서는 프로젝트의 요구사항을 다음 흐름으로 양방향 추적하기 위한 문서이다.

```text
업무 필요
  -> BRD 요구/목표
    -> 사용자 필요
      -> PRD 요구사항(FR/DR/NFR)
        -> Acceptance Criterion
          -> 구현 Issue/PR/Branch
            -> Test / Evidence
```

검토 시에는 반대 방향으로도 추적한다.

```text
Evidence
  -> AC
    -> PRD requirement
      -> BRD requirement/objective
        -> Business need
```

본 프로젝트에서 추적성의 목적은 다음과 같다.

1. 자동차 등록현황, 중고차 매물, FAQ라는 서로 다른 데이터 흐름이 실제 업무 목적과 연결되어 있는지 확인한다.
2. Must 요구사항 중 구현, 검증, evidence가 빠진 고아 요구사항을 찾는다.
3. BRD의 In Scope / Out of Scope 경계를 PRD와 구현 단계에서도 유지한다.
4. source, schema, business key, 갱신 정책이 변경될 때 영향 범위를 확인한다.
5. Issue나 PR이 닫힌 사실과 acceptance criterion의 PASS 판정을 구분한다.

---

## 2. 현재 작성 기준

### 2.1 프로젝트 비즈니스 흐름

프로젝트의 주요 데이터와 업무 목적은 다음과 같이 구분한다.

| 데이터 영역 | 역할 | 주요 사용자 | 업무 결과 |
|---|---|---|---|
| 자동차 등록현황 | 지역별 자동차 시장 규모, 차량 유형 구성, 변화 추이를 파악하는 시장 데이터 | 영업 | 지역 시장 특성을 판단할 수 있는 근거 데이터 제공 |
| 중고차 매물 | 현재 판매 가능한 차량과 공급 현황을 나타내는 영업 데이터 | 영업 | 지역, 가격, 연식, 주행거리, 상태 등의 조건으로 판매 가능 차량 조회 |
| 자동차 기업 FAQ | 제조사별 고객지원 정보를 구조화한 업무 참고 데이터 | 고객지원 | 브랜드, 업무 유형, 카테고리별 FAQ 조회 |
| 파이프라인 운영정보 | 수집, 정제, 검증, 적재 결과와 최신성/오류 상태 | 운영 | 재실행 필요 여부, 실패 지점, 최신 데이터 반영 여부 판단 |

자동차 등록현황과 중고차 매물은 함께 조회할 수 있으나, 등록현황을 직접적인 중고차 수요 데이터로 해석하거나 시스템이 자동으로 판매 지역/가격을 결정하는 기능으로 확장하지 않는다.

FAQ는 고객지원 담당자의 정보 조회를 지원하며 AI 자동응답이나 완전한 CRM 기능으로 확장하지 않는다.

### 2.2 사용자 필요 ID

아래 `UN-*` ID는 이 추적표와 PRD에서 공통으로 사용할 수 있는 사용자 필요 식별자 초안이다. PRD baseline 전에 팀 review를 거쳐 확정한다.

| ID | 사용자 | 사용자 필요 |
|---|---|---|
| `UN-SALES-001` | 영업 담당자 | 지역별 자동차 등록 규모, 차량 유형 구성, 변화 추이와 출처를 확인하고 싶다. |
| `UN-SALES-002` | 영업 담당자 | 현재 판매 가능한 중고차를 지역, 차량 유형, 가격, 연식, 주행거리, 상태 등으로 조회하고 싶다. |
| `UN-SALES-003` | 영업 담당자 | 지역 시장 특성과 현재 매물 공급 현황을 함께 비교하여 영업 판단의 근거로 활용하고 싶다. |
| `UN-CS-001` | 고객지원 담당자 | 제조사/브랜드, 업무 유형, 카테고리별 FAQ와 출처를 빠르게 조회하고 싶다. |
| `UN-OPS-001` | 운영 담당자 | 각 데이터의 마지막 수집 시각, 실행 상태, 처리 건수, 실패 지점을 확인하고 싶다. |
| `UN-OPS-002` | 운영 담당자 | 동일 입력을 안전하게 재실행하고, 실패 후 어디서부터 재개해야 하는지 판단하고 싶다. |
| `UN-MGMT-001` | 경영/검토 역할 | 데이터 제공 범위, 품질/운영 상태, 프로젝트 및 유지보수 비용 산정 근거를 확인하고 싶다. |

---

## 3. ID 사용 원칙

### 3.1 BRD

- 기존 `BR-01` ~ `BR-19`, `BRULE-01` ~ `BRULE-18`, `RISK-01` ~ `RISK-06` ID를 그대로 사용한다.
- baseline 뒤 기존 ID를 재번호화하지 않는다.
- 폐기된 ID를 재사용하지 않는다.
- 의미가 변경되면 `Change_Log.md`에 변경 사유와 영향 범위를 기록한다.
- 이 문서에서는 **현재 제공된 자료만으로 정확한 BR 문장과 번호의 대응을 검증할 수 없는 경우 임의 매핑하지 않고 `TBD (BRD에서 확정)`으로 남긴다.**

### 3.2 PRD

- `FR-*`: 사용자 또는 운영자가 관찰할 수 있는 기능/행동
- `DR-*`: 데이터 grain, key, 필드, 품질, provenance 요구
- `NFR-*`: 멱등성, 보안, source 경계, 관측 가능성, 재시도 등 품질 요구
- 아래 PRD/AC ID는 **프로젝트에 맞춘 후보 ID**이며 `Product_Requirements_Document.md` baseline 때 최종 확정한다.
- PRD에서 다른 ID를 채택하면 이 표는 최종 PRD ID로 교체하고 change log에 최초 연결 변경을 기록한다.

### 3.3 Evidence

- 구현 전 evidence는 `planned`로 기록한다.
- 실제 실행 결과가 없는데 `pass`로 표시하지 않는다.
- live source의 현재 건수를 영구 기대값으로 고정하지 않는다.
- 고정 pass/fail이 필요한 검증은 versioned fixture 또는 명시된 테스트 입력으로 수행한다.

---

## 4. Requirements Traceability Matrix

> `BRD business need / objective`의 `TBD`는 최신 BRD의 실제 `BR-*` 번호를 확인하여 연결해야 하는 자리이다. 요구 의미는 현재 프로젝트 범위에 맞게 먼저 정리해 두었다.

| business need | BRD objective | user need | PRD requirement | AC | implementation | test/evidence | due | evidence_status | BRULE / RISK |
|---|---|---|---|---|---|---|---|---|---|
| `TBD (BRD)` · 분산된 외부 데이터를 반복 수작업으로 확인/가공하는 문제 해소 | `TBD (BRD)` · 지역별 자동차 시장 데이터를 지속적으로 확보 | `UN-SALES-001` | `FR-MKT-COLLECT-001` · 승인된 공공데이터 API에서 자동차 등록현황을 수집한다. | `AC-MKT-COLLECT-001` · 승인 source/parameter로 실행 시 raw가 저장되고 source/기준일 metadata가 남으며 실패 시 부분 적재 여부를 판정할 수 있다. | `TBD (Issue 생성 후 feature/<issue>-market-collect)` | `evidence/market-collect.md` | Day 22 | planned | `TBD (BRULE/RISK)` |
| `TBD (BRD)` · 최신 데이터와 장기 과거 데이터의 갱신 방식이 다름 | `TBD (BRD)` · 최신 데이터 우선 반영과 과거 데이터 backfill을 함께 수행 | `UN-SALES-001`·`UN-OPS-002` | `FR-MKT-BACKFILL-001` · 최신 기준일을 확인하고 신규 구간을 우선 채운 뒤 적재된 마지막 지점부터 과거 데이터를 역순 backfill한다. | `AC-MKT-BACKFILL-001` · 최신 기준일이 기존 적재일과 같으면 마지막 적재 지점부터 계속하고, 다르면 신규 구간을 먼저 채운 뒤 과거 backfill을 이어가며 동일 business key 중복이 증가하지 않는다. | `TBD (Issue 생성 후 feature/<issue>-market-backfill)` | `evidence/market-backfill.md` | Day 22 | planned | `TBD (BRULE/RISK)` |
| `TBD (BRD)` · 시장 데이터의 형식/중복/결측 오류로 조회 신뢰성 저하 가능 | `TBD (BRD)` · 등록현황 데이터를 검증 가능한 구조로 저장 | `UN-SALES-001`·`UN-OPS-001` | `DR-MKT-001` · 시장 데이터의 grain, business key, 필수값, 허용 범위, source provenance를 ERD/Data Contract 기준으로 보장한다. | `AC-MKT-DATA-001` · fixture 기준 필수값 위반, 허용되지 않은 음수/형식 오류, business key 중복이 0건이고 적재 건수와 품질 report의 단위가 일치한다. | `TBD (Issue 생성 후 feature/<issue>-market-quality)` | `output/<run_id>/market-quality-report.json` | Day 22 | planned | `TBD (BRULE/RISK)` |
| `TBD (BRD)` · 수집한 시장 데이터를 업무 조회에 활용해야 함 | `TBD (BRD)` · 지역/시점/차량 유형 기준의 시장 조회 제공 | `UN-SALES-001` | `FR-MKT-QUERY-001` · 지역, 시점, 차량 유형 기준으로 등록 규모/구성/변화 추이를 조회한다. | `AC-MKT-QUERY-001` · versioned fixture에서 지정 지역/기간/유형 조회가 예상 결과와 source 정보를 반환한다. | `TBD (Issue 생성 후 feature/<issue>-market-query)` | `evidence/market-query.md` | Day 23 | planned | `TBD (BRULE)` |
| `TBD (BRD)` · 중고차 판매 사이트의 개별 매물을 반복 확인해야 함 | `TBD (BRD)` · 중고차 매물 정보를 구조화해 지속적으로 확보 | `UN-SALES-002` | `FR-LIST-COLLECT-001` · 승인된 중고차 매물 source에서 허용 범위의 매물 정보를 수집한다. | `AC-LIST-COLLECT-001` · 승인된 범위에서 수집된 매물에 source URL/수집시각이 남고, 차단/접근제한/구조 불일치 시 우회 없이 실패 상태를 기록한다. | `TBD (Issue 생성 후 feature/<issue>-listing-collect)` | `evidence/listing-collect.md` | Day 22 | planned | `TBD (BRULE/RISK)` |
| `TBD (BRD)` · 매물 비교를 위한 공통 구조가 필요 | `TBD (BRD)` · 매물 상태/지역/조건별 조회가 가능한 데이터 구조 제공 | `UN-SALES-002` | `DR-LIST-001` · 매물의 identity/business key, 제조사/모델/연식/주행거리/가격/상태/지역 등 확정 필드를 ERD/Data Contract 기준으로 검증한다. | `AC-LIST-DATA-001` · fixture 적재 후 필수값/타입/중복 규칙 위반이 허용 기준 이내이고 quality report에서 raw/normalized/DB 단위를 구분해 확인할 수 있다. | `TBD (Issue 생성 후 feature/<issue>-listing-quality)` | `output/<run_id>/listing-quality-report.json` | Day 22 | planned | `TBD (BRULE/RISK)` |
| `TBD (BRD)` · 현재 판매 가능한 차량을 조건별로 비교하기 어려움 | `TBD (BRD)` · 매물 상태/지역/가격/연식/주행거리 등 조건 조회 제공 | `UN-SALES-002` | `FR-LIST-QUERY-001` · 판매 상태, 지역, 차량 유형, 가격, 연식, 주행거리 등의 조건으로 매물을 조회한다. | `AC-LIST-QUERY-001` · fixture에서 복수 조건을 적용했을 때 조건을 만족하는 매물만 반환하고 source/provenance를 확인할 수 있다. | `TBD (Issue 생성 후 feature/<issue>-listing-query)` | `evidence/listing-query.md` | Day 23 | planned | `TBD (BRULE)` |
| `TBD (BRD)` · 시장 특성과 현재 공급을 별도 화면/사이트에서 확인해야 함 | `TBD (BRD)` · 영업 담당자가 두 데이터 영역을 함께 비교할 수 있는 조회 제공 | `UN-SALES-003` | `FR-SALES-QUERY-001` · 동일 지역/차량 유형 기준으로 등록현황 요약과 현재 매물 요약을 함께 조회할 수 있게 한다. | `AC-SALES-QUERY-001` · 동일한 지역/차량 유형 입력에서 시장 지표와 매물 공급 결과를 각각의 출처와 단위로 구분하여 반환한다. | `TBD (Issue 생성 후 feature/<issue>-sales-query)` | `evidence/sales-query.md` | Day 23 | planned | `TBD (BRULE)` |
| `TBD (BRD)` · 제조사별 FAQ가 여러 웹사이트에 분산됨 | `TBD (BRD)` · 고객지원 FAQ를 주기적으로 확보 | `UN-CS-001` | `FR-FAQ-COLLECT-001` · 승인된 자동차 기업 FAQ source의 허용 범위만 수집한다. | `AC-FAQ-COLLECT-001` · 허용 source/page에서 질문·답변 후보와 source metadata가 수집되고, 허용 범위 밖 redirect/차단/구조 불일치 시 DB write 없이 실패 상태를 남긴다. | `TBD (Issue 생성 후 feature/<issue>-faq-collect)` | `evidence/faq-collect.md` | Day 22 | planned | `TBD (BRULE/RISK)` |
| `TBD (BRD)` · FAQ를 업무 기준으로 검색하기 어려움 | `TBD (BRD)` · FAQ를 제조사/브랜드/업무유형/카테고리 기준으로 구조화 | `UN-CS-001` | `DR-FAQ-001` · FAQ identity, 질문/답변, 제조사/브랜드, 업무 유형, 카테고리, source, 수집시각 등 확정 필드를 검증한다. | `AC-FAQ-DATA-001` · fixture 적재 후 unique identity 위반 0건, 필수 필드 누락이 허용 기준 이내이며 source와 수집시각을 추적할 수 있다. | `TBD (Issue 생성 후 feature/<issue>-faq-quality)` | `output/<run_id>/faq-quality-report.json` | Day 22 | planned | `TBD (BRULE/RISK)` |
| `TBD (BRD)` · 고객지원 담당자의 반복적인 웹 탐색 업무 | `TBD (BRD)` · FAQ 조건 조회 제공 | `UN-CS-001` | `FR-FAQ-QUERY-001` · 제조사/브랜드, 업무 유형, 카테고리 기준으로 FAQ를 조회한다. | `AC-FAQ-QUERY-001` · fixture에서 지정 company/category/work type 조회가 예상 FAQ 문서와 source를 반환한다. | `TBD (Issue 생성 후 feature/<issue>-faq-query)` | `evidence/faq-query.md` | Day 23 | planned | `TBD (BRULE)` |
| `TBD (BRD)` · source별 갱신 주기가 달라 최신성 확인이 어려움 | `TBD (BRD)` · 데이터별 갱신 주기에 맞는 수집 정책 운영 | `UN-OPS-001` | `FR-SCHEDULE-001` · source별 확정 주기에 따라 수집 작업을 실행하고 마지막 성공/실패 시각을 기록한다. | `AC-SCHEDULE-001` · FAQ 1일 1회, 공공데이터 API 3일 주기 정책이 설정값으로 확인되며 각 실행의 run record가 남는다. 중고차 매물 주기는 PRD에서 확정한다. | `TBD (Issue 생성 후 feature/<issue>-scheduler)` | `evidence/scheduler-run.md` | Day 23 | planned | `TBD (BRULE/RISK)` |
| `TBD (BRD)` · 재실행으로 중복 적재가 발생할 수 있음 | `TBD (BRD)` · 동일 입력의 안전한 재실행 보장 | `UN-OPS-002` | `NFR-IDEMP-001` · 동일 입력을 재실행해도 business row/document가 중복 추가되지 않는다. | `AC-IDEMP-001` · 동일 fixture를 두 번 실행해도 고유 business key/document 수가 불필요하게 증가하지 않고 두 run record는 각각 남는다. | `TBD (Issue 생성 후 feature/<issue>-idempotency)` | `evidence/retry-idempotency.md` | Day 23 | planned | `TBD (BRULE/RISK)` |
| `TBD (BRD)` · 외부 source 구조/접근정책 변경으로 잘못된 적재 가능 | `TBD (BRD)` · 승인되지 않은 source 상태에서는 fail-closed | `UN-OPS-001`·`UN-OPS-002` | `NFR-SOURCE-001` · robots/접근 제한, 403/429, allowlist 밖 redirect, license 확인 실패, schema/selector 불일치 시 우회하거나 잘못된 write를 수행하지 않는다. | `AC-SOURCE-001` · failure fixture 또는 차단 조건에서 DB write 전후 count가 동일하고 `blocked` 또는 `failed`와 sanitized 원인이 기록된다. | `TBD (Issue 생성 후 feature/<issue>-source-guard)` | `evidence/source-guard.md` | Day 22 | planned | `TBD (BRULE/RISK)` |
| `TBD (BRD)` · 수집 성공 여부와 실패 위치를 통합적으로 확인하기 어려움 | `TBD (BRD)` · run/stage 상태와 처리 결과 관측 가능 | `UN-OPS-001` | `NFR-OBS-001` · run과 stage별 status, count unit, 시작/종료 시각, sanitized error를 기록한다. | `AC-OBS-001` · 성공/실패 fixture에서 각 stage의 status와 단위별 count를 확인할 수 있고 secret/민감정보가 error에 노출되지 않는다. | `TBD (Issue 생성 후 feature/<issue>-observability)` | `logs/<run_id>.jsonl`, `evidence/observability.md` | Day 23 | planned | `TBD (BRULE/RISK)` |
| `TBD (BRD)` · 일시적 네트워크/HTTP 오류가 전체 파이프라인 실패로 이어질 수 있음 | `TBD (BRD)` · 제한된 재시도와 실패 판정 제공 | `UN-OPS-002` | `NFR-RETRY-001` · 재시도 가능한 오류에만 bounded retry를 적용하고 최종 실패를 기록한다. | `AC-RETRY-001` · retry fixture에서 설정된 최대 횟수를 초과하지 않으며 성공 또는 최종 실패 상태가 run record에 남는다. | `TBD (Issue 생성 후 feature/<issue>-retry-policy)` | `evidence/retry-idempotency.md` | Day 23 | planned | `TBD (BRULE/RISK)` |
| `TBD (BRD)` · 데이터 품질 이상을 업무 사용 전에 확인해야 함 | `TBD (BRD)` · 중복/결측/형식/범위 검증과 이슈 가시화 | `UN-OPS-001`·`UN-MGMT-001` | `NFR-QUALITY-001` · 각 데이터셋별 확정 품질 규칙을 실행하고 위반 건수와 판정을 기록한다. | `AC-QUALITY-001` · fixture 실행 시 데이터셋별 rule 결과, count unit, PASS/FAIL, 위반 sample 또는 sanitized 사유가 quality report에 남는다. | `TBD (Issue 생성 후 feature/<issue>-quality-report)` | `output/<run_id>/quality-report.json` | Day 23 | planned | `TBD (BRULE/RISK)` |
| `TBD (BRD)` · 개인정보/secret 노출은 프로젝트 범위와 운영 안전성을 침해 | `TBD (BRD)` · 개인정보 배제와 credential 분리 | `UN-OPS-001`·`UN-MGMT-001` | `NFR-SECRET-001` · 개인정보, API key, DB URI, AWS credential, private endpoint를 tracked file/log/evidence에 남기지 않는다. | `AC-SECRET-001` · repository/evidence/log secret scan에서 의심 패턴 0건이며 개인정보 탐지 시 reject 또는 검토 상태로 처리한다. | `TBD (Issue 생성 후 chore/<issue>-security-review)` | `evidence/security-review.md` | Day 23 | planned | `TBD (BRULE/RISK)` |
| `TBD (BRD)` · 검토자가 데이터의 출처와 처리 결과를 확인해야 함 | `TBD (BRD)` · source/provenance와 처리 이력 감사 가능 | `UN-MGMT-001`·`UN-OPS-001` | `DR-PROVENANCE-001` · 데이터셋별 source 식별자, 수집시각/기준일, run_id, 처리 결과를 추적 가능하게 보존한다. | `AC-PROVENANCE-001` · 샘플 record/document에서 원 source와 해당 run/evidence를 역추적할 수 있다. | `TBD (Issue 생성 후 feature/<issue>-provenance)` | `evidence/provenance-check.md` | Day 23 | planned | `TBD (BRULE/RISK)` |
| `TBD (BRD)` · 솔루션 도입/운영 비용 판단 근거 필요 | `TBD (BRD)` · 솔루션 금액, 유지보수/서비스 비용 산정 근거 제공 | `UN-MGMT-001` | `TBD (PRD/산출물 경계 확정)` · 실제 빌링 기능이 아니라 비용 산정/제안 산출물로 관리한다. | `TBD` · 비용 항목, 산정 기준, 가정, 제외 범위가 문서에 명시되고 실제 청구/회계 실행 기능이 포함되지 않는다. | `TBD (docs 또는 cost-estimate 산출물)` | `evidence/cost-review.md` 또는 비용 산정 문서 | Day 23 | planned | `TBD (BRULE/RISK)` |

---

## 5. 후보 PRD Requirement Catalog

> 아래 ID는 추적표 작성을 위한 **초안**이다. 최종 `Product_Requirements_Document.md`가 다른 식별자를 채택하면 PRD를 정본으로 하고 이 문서의 ID를 동기화한다.

### 5.1 Functional Requirements

| ID | 상태 | 요구사항 요약 | 주요 사용자 |
|---|---|---|---|
| `FR-MKT-COLLECT-001` | Must do | 공공 자동차 등록현황 데이터를 승인 source에서 수집 | 영업/운영 |
| `FR-MKT-BACKFILL-001` | Must do | 최신 구간 우선 적재 후 과거 데이터를 이어서 backfill | 영업/운영 |
| `FR-MKT-QUERY-001` | Must do | 지역/시점/차량 유형별 시장 데이터 조회 | 영업 |
| `FR-LIST-COLLECT-001` | Must do | 승인된 중고차 매물 source 수집 | 영업/운영 |
| `FR-LIST-QUERY-001` | Must do | 상태/지역/가격/연식/주행거리 등 조건별 매물 조회 | 영업 |
| `FR-SALES-QUERY-001` | Must do | 동일 기준으로 시장 지표와 매물 공급 현황 비교 조회 | 영업 |
| `FR-FAQ-COLLECT-001` | Must do | 승인된 자동차 기업 FAQ source 수집 | 고객지원/운영 |
| `FR-FAQ-QUERY-001` | Must do | 제조사/브랜드/업무유형/카테고리별 FAQ 조회 | 고객지원 |
| `FR-SCHEDULE-001` | Must do | source별 주기에 맞는 수집 실행과 마지막 상태 기록 | 운영 |

### 5.2 Data Requirements

| ID | 상태 | 요구사항 요약 |
|---|---|---|
| `DR-MKT-001` | Must do | 시장 데이터 grain/key/필수값/provenance 품질 보장 |
| `DR-LIST-001` | Must do | 매물 identity/조건조회 필드/상태/provenance 품질 보장 |
| `DR-FAQ-001` | Must do | FAQ identity/분류/질문답변/source 품질 보장 |
| `DR-PROVENANCE-001` | Must do | source/run/기준일/처리결과의 역추적 가능성 보장 |

### 5.3 Non-functional Requirements

| ID | 상태 | 요구사항 요약 |
|---|---|---|
| `NFR-IDEMP-001` | Must do | 동일 입력 재실행 시 business 데이터 중복 방지 |
| `NFR-SOURCE-001` | Must do | source 경계/구조/접근정책 불명확 시 fail-closed |
| `NFR-OBS-001` | Must do | run/stage 상태, count, error 관측 가능 |
| `NFR-RETRY-001` | Must do | 제한된 재시도와 최종 실패 판정 |
| `NFR-QUALITY-001` | Must do | 데이터셋별 품질 규칙과 report 생성 |
| `NFR-SECRET-001` | Must do | 개인정보/credential/private endpoint 비노출 |

---

## 6. Candidate Acceptance Criteria Catalog

> AC는 `Given / When / Then / Evidence`를 기준으로 pass/fail이 가능해야 한다. 아래는 핵심 AC의 판정 문장 초안이다.

### `AC-MKT-BACKFILL-001`

- Given: 시장 데이터 저장소에 마지막 적재 기준일과 일부 과거 데이터가 존재한다.
- When: 공공데이터 수집 작업을 다시 실행한다.
- Then:
  - source의 최신 기준일이 기존 최신 적재일과 같으면 기존 마지막 적재 지점부터 과거 방향으로 수집을 계속한다.
  - source 최신 기준일이 더 새로우면 기존 최신 적재일까지 신규 구간을 먼저 채운 후 과거 backfill을 이어간다.
  - 동일 business key의 중복 수가 증가하지 않는다.
- Evidence: `evidence/market-backfill.md`, 실행 전후 기준일/count/duplicate 검사 결과
- Evidence status: `planned`

### `AC-IDEMP-001`

- Given: 동일한 versioned fixture와 격리된 테스트 저장소가 주어진다.
- When: 같은 입력으로 pipeline을 두 번 실행한다.
- Then: 고유 business key/document 수는 불필요하게 증가하지 않고 두 run record는 각각 남는다.
- Evidence: `evidence/retry-idempotency.md`
- Evidence status: `planned`

### `AC-SOURCE-001`

- Given: 403/429, 접근/robots 제한, allowlist 밖 redirect, license 확인 실패, selector 0건 또는 schema mismatch 중 하나가 발생한다.
- When: collector를 실행한다.
- Then: 제한 우회나 잘못된 DB write를 수행하지 않고 `blocked` 또는 `failed` 상태와 sanitized 원인을 남긴다.
- Evidence: `evidence/source-guard.md`, write 전후 count, sanitized log
- Evidence status: `planned`

### `AC-QUALITY-001`

- Given: 정상 fixture와 의도적으로 결측/중복/형식 오류를 포함한 failure fixture가 주어진다.
- When: 품질 검증을 실행한다.
- Then: 데이터셋과 rule별 PASS/FAIL, 위반 건수, count unit, 검토 가능한 sample 또는 sanitized 사유가 기록된다.
- Evidence: `output/<run_id>/quality-report.json`
- Evidence status: `planned`

### `AC-OBS-001`

- Given: 성공 run과 실패 run fixture가 각각 존재한다.
- When: pipeline을 실행한다.
- Then: run/stage별 status, 시작/종료 시각, count unit, sanitized error가 기록되어 운영자가 실패 지점과 재실행 필요 여부를 판단할 수 있다.
- Evidence: `logs/<run_id>.jsonl`, `evidence/observability.md`
- Evidence status: `planned`

---

## 7. Scope Guardrail Traceability

다음 항목은 현재 프로젝트의 **Out of Scope 경계**로 취급한다. 해당 기능이 PRD/Issue에 등장하면 BRD change review 없이는 구현하지 않는다.

| guardrail | 현재 처리 |
|---|---|
| 개인정보 처리 | 제외 |
| 실제 자동차 계약/결제 | 제외 |
| 금융/할부 | 제외 |
| 보험 | 제외 |
| 실제 명의이전 | 제외 |
| 자동 가격 결정 또는 시세 예측 | 제외 |
| 개인화 추천 | 제외 |
| 자동 판매지역 결정 | 제외 |
| FAQ 기반 AI 자동응답 | 제외 |
| 완전한 CRM/상담 시스템 | 제외 |
| 실제 회계/청구 실행 | 제외 |
| 대규모 실시간 처리 | 제외 |

비용 관련 요구는 **솔루션 금액 및 유지보수/서비스 비용의 산정 근거**를 만드는 범위로 제한하며 실제 billing/accounting system 구현과 구분한다.

---

## 8. Git Flow / Implementation Link 규칙

implementation 열은 실제 GitHub Issue가 생성된 뒤 다음 형식으로 교체한다.

```text
<type>/<issue-number>-<short-description>
```

예시 형식만 사용하며 실제 Issue 번호를 문서에서 임의 생성하지 않는다.

```text
feature/<issue>-market-collect
feature/<issue>-faq-query
fix/<issue>-listing-parser
chore/<issue>-security-review
```

적용 원칙:

1. 작업 branch는 최신 `develop`에서 생성한다.
2. `main`, `develop`에 직접 commit/push하지 않는다.
3. 기능/일반 변경 PR은 `develop`을 대상으로 한다.
4. PR에는 담당 PRD requirement ID와 AC ID를 적는다.
5. review, CI/test, conflict 해결 후 merge commit 방식으로 병합한다.
6. 공유 branch history를 rebase 또는 force-push하지 않는다.
7. Issue/PR이 닫혀도 AC evidence가 없으면 `evidence_status=pass`로 바꾸지 않는다.

---

## 9. Link Integrity Review

### 9.1 Review fields

- traceability_version: `v0.1`
- brd_reference: `Business_Requirements_Document.md`
- prd_reference: `TBD`
- candidate_requirement_count: `19`
- must_requirement_count: `19`
- must_with_ac_count: `19 (candidate AC 기준)`
- brd_id_mapping_complete: `NO`
- orphan_must_requirement_count: `TBD - BRD/PRD ID 확정 후 계산`
- premature_pass_count: `0`
- evidence_status_allowed: `planned | pass | fail`
- reviewer_role: `TBD`
- reviewed_at: `TBD (ISO-8601)`
- link_integrity_review: `FAIL until BRD/PRD IDs are fully mapped`

### 9.2 PASS 조건

다음 조건을 모두 충족해야 `link_integrity_review: PASS`로 변경한다.

- [ ] 모든 `BR-01~BR-19` 중 PRD로 내려와야 하는 요구가 최소 한 행 이상 추적된다.
- [ ] 필요한 `BRULE-*`, `RISK-*`가 관련 행에 연결된다.
- [ ] 모든 Must FR/DR/NFR이 실제 BRD 요구 또는 목표로 backward trace된다.
- [ ] 모든 Must PRD requirement에 최소 1개의 pass/fail 가능한 AC가 있다.
- [ ] 모든 AC에 implementation link 또는 계획, evidence path, due가 있다.
- [ ] 아직 실행하지 않은 evidence는 `planned`이다.
- [ ] 실제 실행 증거 없이 `pass`인 행이 0건이다.
- [ ] orphan Must requirement가 0건이다.
- [ ] Out of Scope 항목이 PRD/Issue에 신규 기능으로 포함되지 않았다.
- [ ] reviewer, 검토일, version이 기록되어 있다.

---

## 10. Forward / Backward Review 절차

### Forward review

각 핵심 업무 필요에서 시작해 다음 연결이 끊기지 않는지 확인한다.

```text
BRD
-> User Need
-> PRD Requirement
-> AC
-> Issue / PR / Branch
-> Test / Evidence
```

### Backward review

각 evidence에서 시작해 다음 질문에 답한다.

1. 이 evidence는 어떤 AC를 판정하는가?
2. 그 AC는 어떤 PRD requirement를 검증하는가?
3. 그 PRD requirement는 어떤 BRD 요구/목표에서 도출되었는가?
4. 그 BRD 요구는 어떤 이해관계자의 업무 결과를 위한 것인가?

하나라도 답할 수 없으면 orphan 또는 잘못된 연결 후보로 표시한다.

---

## 11. 변경 영향 추적 규칙

다음 항목이 변경되면 해당 collector만 수정하고 끝내지 않는다.

| 변경 대상 | 함께 검토할 영향 |
|---|---|
| 공공 API field / 기준일 / pagination / 호출 제한 | source registry, backfill 전략, data contract, business key, schema, 품질 rule, 과거 적재 데이터 |
| 중고차 사이트 selector / 페이지 구조 / 상태값 | collector, parser, listing schema, query, fixture, source policy |
| FAQ selector / category / source / license | collector, FAQ data contract, identity/hash, query, 기존 raw/normalized 데이터, evidence |
| business key | 중복 제거, idempotency, unique constraint/index, migration/backfill, regression fixture |
| 데이터 갱신 주기 | scheduler, 운영 SLA, 최신성 판정, run log, 비용 |
| MySQL/MongoDB schema | ERD/Data Contract, repository interface, query, index, migration, 테스트 |
| 비용 가정 | 비용 산정 문서, AWS resource 가정, 유지보수 범위, 경영 검토 evidence |

변경 요청에는 최소 다음을 기록한다.

```text
CR-ID
reason
before / after
affected BR / BRULE / RISK
affected PRD requirement / AC
affected source / schema / schedule
migration or backfill required?
decision
owner
applied version
```

---

## 12. 다음 확정 작업

이 문서를 프로젝트 baseline 수준으로 올리기 위해서는 다음 순서로 빈 연결을 제거한다.

1. 최신 `Business_Requirements_Document.md`를 기준으로 각 행의 `TBD (BRD)`를 실제 `BR-*` ID로 교체한다.
2. 관련 업무 규칙과 위험을 `BRULE-*`, `RISK-*`에 연결한다.
3. `Product_Requirements_Document.md`에서 최종 FR/DR/NFR ID를 확정하고 후보 ID와 동기화한다.
4. 각 PRD requirement에 Given/When/Then/Evidence 형식의 AC를 확정한다.
5. GitHub Issue 생성 후 implementation 열을 실제 branch/Issue/PR 링크로 교체한다.
6. 실행 전에는 `planned`, 실행 후 evidence를 검토하여 `pass` 또는 `fail`로 판정한다.
7. forward/backward review 후 orphan Must requirement가 0건이면 baseline review를 완료한다.

---

## 13. Review Evidence Template

```yaml
review_id: REV-REQ-001
traceability: RTM-MLO-01-03-001@v0.1
brd: Business_Requirements_Document.md
prd: TBD
reviewer_role: TBD
reviewed_at: TBD
must_requirement_count: 19
must_with_ac_count: 19
brd_id_mapping_complete: false
orphan_must_requirement_count: TBD
premature_pass_count: 0
secret_suspect_count: TBD
scope_guardrail_violation_count: TBD
review_result: FAIL
open_questions:
  - id: OQ-RTM-001
    question: 최신 BRD의 BR-01~BR-19 문장과 본 추적표 행을 확정 매핑한다.
    owner: TBD
  - id: OQ-RTM-002
    question: PRD 최종 FR/DR/NFR 및 AC ID를 확정한다.
    owner: TBD
  - id: OQ-RTM-003
    question: 중고차 매물 수집 주기를 확정한다.
    owner: TBD
```

`review_result`는 BRD/PRD ID 연결이 끝나고 실제 link integrity review를 수행한 뒤에만 `PASS`로 변경한다.
