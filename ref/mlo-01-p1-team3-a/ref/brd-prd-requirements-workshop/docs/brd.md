# BRD · 자동차 등록·FAQ 데이터 파이프라인

> starter_id: `encore.chapter1.brd-prd-requirements-workshop.starter`  
> starter_version: `v1`  
> 작성 규칙: `<TODO>`만 채우고 실제 credential·private endpoint·개인정보는 쓰지 않는다.

- document_id: `BRD-VF-001`
- version: `v1`
- document_state: `Draft`
- owner_role: `<TODO>`
- reviewer_roles: [`<TODO>`]
- baseline_date: `<TODO: YYYY-MM-DD>`
- provenance: `사용자 제공 자동차 등록·기업 FAQ 수행계획을 우선하고, 과정 PDF의 일반 24시간 프로젝트 계약 및 기존 prj/1st 버전과의 차이는 docs/change-log.md에 기록한다.`

## 1. 배경과 현재 문제

월별 자동차 통계와 FAQ를 사람이 따로 복사·정리하면 실행 범위, 출처, 품질검사와 변경 이력을 같은 방법으로 재현하기 어렵다.

<TODO: 구현 방법이 아니라 현재 업무 문제를 2~3문장으로 보완>

## 2. 이해관계자와 필요한 결과

| ID | 이해관계자 | 필요한 업무 결과 |
|---|---|---|
| `STK-AN-001` | 분석 담당자 | 기준월·지역·차종별 자동차 결과와 출처를 함께 확인한다. |
| `STK-FAQ-001` | FAQ 사용자 | 회사·category별 질문·답변과 출처를 함께 확인한다. |
| `STK-OPS-001` | pipeline 운영자 | 실패 지점과 안전한 재실행 필요 여부를 판정한다. |
| `STK-AUD-001` | 검토자 | source·품질·처리 결과를 evidence로 감사한다. |

## 3. 업무 목표와 측정 방법

| ID | 업무 목표 | 측정 방법 |
|---|---|---|
| `BR-OBJ-001` | 분석 담당자가 자동차 결과와 출처를 함께 확인한다. | `<TODO: pass/fail 가능한 이해관계자 결과>` |
| `BR-OBJ-002` | FAQ 사용자가 질문·답변과 출처를 함께 확인한다. | `<TODO: pass/fail 가능한 이해관계자 결과>` |
| `BR-OBJ-003` | 운영 담당자가 재실행 필요 여부와 실패 지점을 판단한다. | 운영 시나리오에서 두 판정 근거가 모두 보인다. |
| `BR-OBJ-004` | 검토자가 데이터와 실행의 출처·처리 결과를 감사한다. | 검토 시나리오의 근거 항목 누락이 0건이다. |

## 4. In scope

- `BR-SCOPE-001`: 승인된 자동차 기준월 1개를 수집·정제·저장·조회한다.
- `BR-SCOPE-002`: allowlist FAQ page 최대 2개를 제한 수집·정제·저장·조회한다.
- `BR-SCOPE-003`: 한 번 실행, 안전한 재실행, 예약 1회와 sanitized evidence를 검증한다.
- `BR-SCOPE-004`: 작은 `output/sample/dashboard.json` 인계 snapshot을 만든다.

## 5. Out of scope

- `BR-OOS-001`: 차량번호·차대번호·소유자·연락처 같은 개인정보
- `BR-OOS-002`: 로그인·CAPTCHA 뒤 콘텐츠와 robots·403·429 우회
- `BR-OOS-003`: 웹 dashboard·UI 개발·배포와 ML 모델
- `BR-OOS-004`: production HA·DR·자동 failover·CI/CD

## 6. 업무 규칙·제약·가정

- `BR-CON-001`: 수행계획에서 지정한 MySQL·MongoDB 저장 요구를 충족한다.
- `BR-CON-002`: 실제 key·credential·private endpoint는 문서와 Git에 기록하지 않는다.
- `BR-CON-003`: live source 승인 여부와 무관하게 official-shape fixture로 Must do를 재현한다.
- `BR-ASM-001`: starter v1을 제공하고 본편 100~150분에 source registry의 owner·범위·fallback을 검증한다.

## 7. 위험·대응·미결 질문

| ID | 발생 조건 | 영향 | 대응 | owner | 상태 |
|---|---|---|---|---|---|
| `BR-RISK-001` | API key 승인 지연 | live 수집 불가 | official-shape fixture 또는 승인 XLSX 사용 | `<TODO>` | open |
| `BR-RISK-002` | robots·license·schema 변경 | 수집·재배포 경계 불명확 | write 없이 중단하고 변경 검토 | `<TODO>` | open |
| `BR-OQ-001` | `<TODO: 아직 결정하지 못한 질문>` | `<TODO>` | `<TODO>` | `<TODO>` | open |

## 8. 검토 기록과 변경 원칙

| reviewed_at | reviewer_role | review_result | note |
|---|---|---|---|
| `<TODO>` | `<TODO>` | `PASS | FAIL` | `<TODO>` |

- peer review가 끝나면 `document_state: Baselined`로 바꾼다.
- baseline 뒤 요구 의미 변경은 `docs/change-log.md` 한 곳에 기록한다.
- 실제 회사의 경영진 승인을 받지 않았다면 승인 서명을 꾸미지 않는다.
