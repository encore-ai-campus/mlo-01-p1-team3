# Day 21 · 1일차 팀 프로젝트 진행 가이드

> 이 문서는 **“오늘 팀원 4명이 무엇을 해야 하는지”**를 처음 프로젝트를 진행하는 사람도 이해할 수 있도록 풀어서 설명한 가이드입니다.  
> 핵심은 **코드를 많이 만드는 것보다, 내일부터 각자 구현을 시작해도 서로 다른 방향으로 가지 않도록 기준을 맞추는 것**입니다.

---

# 0. 오늘의 목표 한 줄

오늘이 끝났을 때 팀원 4명이 아래 질문에 **같은 답**을 할 수 있어야 합니다.

- 우리는 **왜** 이 프로젝트를 만드는가?
        - 1차 팀 프로젝트의 일환으로써 "자동차 제조사 영업·고객지원 데이터 통합 솔루션" 으로써 정제된 데이터를 판매하는 것을 목적으로 함.
- 어떤 데이터를 **어디서** 가져오는가?
        - 국토교통 통계누리 (월별 자동차 등록 현황), 강사님 제공 FAQ 사이트 (FAQ 비정형 데이터)
- 어떤 기능을 **반드시** 만들어야 하는가?
        - 데이터 수집, 전처리 및 정재, 적재 까지의 전체 자동화 파이프라인
- 데이터가 정상인지 **어떻게 판단**하는가?
        - Raw 데이터와 수치비교, 파이프라인에서 과정별 Rows 비교
- 같은 데이터를 두 번 넣었을 때 **중복되지 않는가?**
        - 멱등성을 고려하여 파이프라인 설계
        - 낙관적 락 방식 구현 (읽기 시 버전과 트랜젝션 commit 직전 버전 확인, 버전이 같을경우 commit, 버전이 다를경우 rollback 후 재시도)
- 오류가 발생했을 때 **어디에서 실패했는지 알 수 있는가?**
        - 전체 파이프라인 로그 작성 및 수집을 통해 이슈가 발생한 레이어 특정 가능
- 누가 어떤 기능을 맡고, Git에서 **어떤 방식으로 합칠 것인가?**
        - Git Flow 방식. (참고:docs/GitHub_Workflow_Strategy.md)
- 나중에 “이 기능은 왜 만들었지?”라고 물었을 때 **요구사항부터 코드와 테스트 결과까지 추적할 수 있는가?**

---

# 1. 시작 20~30분 — 팀 공통 합의

먼저 네 명이 함께 프로젝트의 **경계**를 확정합니다.

## 1-1. 왜 이걸 먼저 하나?

프로젝트 초반에 가장 흔한 문제는 각자 생각하는 프로젝트 범위가 다른 것입니다.

예를 들어:

- A: “전국 자동차 데이터를 전부 가져오는 줄 알았는데?”
- B: “최근 한 달 데이터만 하는 거 아니었어?”
- C: “FAQ 사이트 직접 크롤링하는 거 아니었어?”
- D: “강사님 서버에서 받는 거라던데?”

이 상태로 코딩을 시작하면 나중에 코드를 합칠 때 구조가 전부 달라질 수 있습니다.

그래서 **오늘 첫 번째 작업은 코딩이 아니라 합의**입니다.

## 1-2. 오늘 확정할 항목

- 프로젝트 범위: **자동차 기준월 1개 + 승인 FAQ page 최대 2개**
- 자동차 Source 후보 및 담당자
- 강사 제공 FAQ Source의 접속 방식/형식 확인
- MySQL 담당 / MongoDB 담당 / Pipeline·AWS 담당 / 문서·검증 담당
- Git 작업 규칙
  - Requirement ID 기반 Issue
  - `feature/*`, `fix/*`, `docs/*`
  - PR → Peer Review → Merge
- 문서 reviewer 결정

## 1-3. 용어 설명

### Source
데이터의 **출처**입니다.

예:
- 공공데이터 API
- CSV 파일
- 강사님이 제공하는 FAQ 서버

### Reviewer
작성자가 아닌 다른 팀원이 문서나 코드를 확인하는 사람입니다.

### Peer Review
팀원이 서로의 문서나 코드를 검토하는 과정입니다.

---

# 2. BRD 작성 — `docs/Business_Requirements_Document.md`

**전원이 같이 결정해야 하는 문서입니다.**

## 2-1. BRD가 뭐야?

BRD는 **Business Requirements Document**의 약자입니다.

쉽게 말하면:

> “왜 이 프로젝트를 만들고, 누구에게 어떤 결과가 필요한가?”

를 정리하는 문서입니다.

BRD에서는 **구현 방법을 자세히 쓰지 않습니다.**

예를 들어:

❌ 잘못된 예

```text
Python requests로 API를 호출하고
pandas로 전처리한 뒤
PyMySQL로 RDS에 INSERT 한다.
```

이건 **기술 설계**에 가까운 내용입니다.

✅ BRD에 적합한 예

```text
분석 담당자가 기준월·지역·차종별 자동차 등록 결과를
출처와 함께 확인할 수 있어야 한다.
```

## 2-2. 작성할 항목

```text
배경과 현재 문제
이해관계자와 필요한 결과
업무 목표와 측정 방법
In Scope
Out of Scope
업무 규칙 / 제약 / 가정
위험 / 대응 / 미결 질문
검토 기록 / 변경 원칙
```

## 2-3. 각각 무슨 뜻인가?

### 배경과 현재 문제
왜 이 프로젝트가 필요한지를 적습니다.

예:

```text
자동차 데이터와 FAQ 데이터의 수집·정제·검증·저장이
각각 수작업으로 진행될 경우 재현성이 떨어지고,
중복·결측·출처 확인이 어려울 수 있다.
```

### 이해관계자
이 시스템의 결과를 사용하는 사람입니다.

이번 프로젝트에서는 예를 들어:

- 자동차 분석 담당자
- FAQ 사용자
- Pipeline 운영자
- 검토자

### 업무 목표
“잘 만든다”처럼 모호하게 쓰면 안 됩니다.

✅ 좋은 예

```text
분석 담당자가 기준월·지역·차종별 자동차 등록 결과와
데이터 출처를 함께 확인할 수 있다.
```

### In Scope
이번 프로젝트에서 **할 것**입니다.

예:

```text
자동차 기준월 1개 수집
FAQ 승인 page 최대 2개 수집
MySQL / MongoDB 적재
지정 조회 검증
```

### Out of Scope
이번 프로젝트에서 **하지 않을 것**입니다.

예:

```text
웹 UI
ML
Production HA
개인정보 수집
로그인/CAPTCHA 우회
```

---

# 3. PRD 작성 — `docs/Product_Requirements_Document.md`

BRD가 “왜?”라면 PRD는:

> “그 목표를 달성하기 위해 제품이 실제로 무엇을 해야 하는가?”

를 정리하는 문서입니다.

## 3-1. 요구사항 종류

```text
FR = 기능 요구사항
DR = 데이터 요구사항
NFR = 비기능 요구사항
```

### FR — Functional Requirement
시스템이 해야 하는 **기능**입니다.

예:

```text
자동차 raw 데이터를 수집한다.
```

### DR — Data Requirement
데이터가 가져야 하는 **구조와 품질 조건**입니다.

예:

```text
자동차 등록대수는 음수가 될 수 없다.
```

### NFR — Non-Functional Requirement
보안, 안정성, 재실행, 로그 등 **품질 특성**입니다.

예:

```text
동일한 입력을 두 번 실행해도 중복 데이터가 추가되지 않는다.
```

## 3-2. 담당자별 예시

### 자동차 담당

```text
FR-VEH-COLLECT-001
FR-VEH-TRANSFORM-001
DR-VEH-001
```

### FAQ 담당

```text
FR-FAQ-COLLECT-001
DR-FAQ-001
```

### 운영 / Pipeline 담당

```text
FR-RUN-001
NFR-IDEMP-001
NFR-OBS-001
NFR-RETRY-001
NFR-SOURCE-001
```

### 보안

```text
NFR-SECRET-001
```

## 3-3. 각 요구사항에 꼭 들어갈 것

- ID
- 상태
- owner
- 연결 BRD
- AC
- due day

### owner란?
그 요구사항을 구현하거나 검증할 **주 담당 역할**입니다.

### due day란?
언제까지 검증 증거를 만들지 정하는 것입니다.

---

# 4. Acceptance Criteria 작성

## 4-1. Acceptance Criteria가 뭐야?

줄여서 **AC**라고 합니다.

쉽게 말하면:

> “이 요구사항을 구현했다고 인정하려면 어떤 조건을 통과해야 하는가?”

입니다.

“정상 동작한다”만 쓰면 사람마다 기준이 다릅니다.

그래서 다음 네 부분으로 나눕니다.

```text
Given
When
Then
Evidence
```

## 4-2. 뜻

### Given
테스트를 시작하기 전 준비 상태

### When
어떤 행동을 했는지

### Then
무엇이 나와야 성공인지

### Evidence
그 성공을 무엇으로 증명할지

---

## 4-3. 정상 실행 예시

```text
Given
정상 fixture/source가 준비됨

When
pipeline 실행

Then
정상 record가 저장되고 count가 일치

Evidence
실행 결과 / count / JSON / 로그
```

---

## 4-4. 동일 입력 재실행 예시

```text
Given
동일한 입력

When
같은 pipeline을 두 번 실행

Then
Business Key 수 증가 없음
Run record는 각각 존재

Evidence
실행 전후 count / duplicate 검사
```

### Business Key란?

데이터를 업무적으로 **같은 데이터인지 판별하는 기준 조합**입니다.

예를 들어 자동차 데이터에서:

```text
기준월 + 지역 + 세부지역 + 차종
```

이 조합이 같다면 같은 업무 데이터라고 판단할 수 있습니다.

정확한 Business Key는 실제 Source 구조를 보고 확정합니다.

---

## 4-5. Source 차단 예시

```text
Given
403 / 429 / schema mismatch / 허용범위 이탈

When
collector 실행

Then
우회하지 않음
DB write 0건
blocked/failed 상태 기록

Evidence
failure log / DB 전후 count
```

### 왜 DB Write를 하지 않나?

Source가 이상한데도 데이터를 저장하면
**잘못된 데이터가 정상 데이터처럼 DB에 남을 수 있기 때문**입니다.

즉, 실패 자체보다 더 위험한 것은:

> 실패했는데도 성공한 것처럼 데이터가 저장되는 것

입니다.

---

# 5. 샘플 데이터(Fixture) 준비

## 5-1. Fixture가 뭐야?

Fixture는 테스트를 위해 미리 만들어 둔 **고정 샘플 데이터**입니다.

실제 공공데이터 API는 오늘 276건을 주다가
다음 달에는 300건을 줄 수도 있습니다.

그러면 테스트 기준이 계속 바뀝니다.

그래서 우리가 직접 만든 작은 데이터를 사용합니다.

예:

```text
fixtures/
├── valid/
│   ├── vehicle_sample.csv
│   └── faq_sample.json
└── invalid/
    ├── vehicle_bad_sample.csv
    └── faq_bad_sample.json
```

## 5-2. valid 데이터

정상적으로 DB에 저장되어야 하는 데이터입니다.

## 5-3. invalid 데이터

일부러 오류를 넣은 데이터입니다.

예:

- 지역 누락
- 음수 등록대수
- 날짜 형식 오류
- 질문 누락
- 중복 데이터

이걸 이용해 Validation이 실제로 작동하는지 확인합니다.

---

# 6. 추적표 작성 — `docs/Requirements_Traceability.md`

## 6-1. 왜 필요한가?

프로젝트가 진행되면 이런 질문이 생깁니다.

> “이 코드 왜 만들었지?”

추적표가 있으면 이렇게 따라갈 수 있습니다.

```text
Business Need
↓
BRD Objective
↓
User Need
↓
PRD Requirement
↓
AC
↓
Implementation
↓
Evidence
```

즉,

> 문제 → 목표 → 요구사항 → 구현 → 테스트 결과

가 연결됩니다.

## 6-2. 예시

```text
BR-OBJ-001
→ UN-AN-001
→ DR-VEH-001
→ AC-VEH-DATA-001
→ feature/vehicle-transform
→ output/<run_id>/quality-report.json
→ Day 22
→ planned
```

### planned란?

아직 테스트하지 않았지만
**앞으로 이 경로에 Evidence를 만들 예정이라는 뜻**입니다.

오늘 구현하지 않은 것을 `PASS`라고 적으면 안 됩니다.

---

# 7. Git Flow 세팅

## 7-1. 왜 Git Flow가 필요한가?

4명이 동시에 `main`을 수정하면 충돌하거나
다른 사람의 작업을 덮어쓸 수 있습니다.

그래서 각자 Branch에서 작업합니다.

```text
Requirement
    ↓
Issue
    ↓
feature/*
    ↓
Commit / Push
    ↓
PR
    ↓
Peer Review
    ↓
main Merge
```

## 7-2. 아주 쉽게 설명하면

### Issue
“무슨 일을 할지” 등록하는 작업표

### Branch
내 작업을 다른 사람 코드와 분리하는 작업 공간

### Commit
변경 내용을 저장하는 작은 기록

### Push
내 컴퓨터의 Commit을 GitHub에 올리는 것

### Pull Request (PR)
“내 작업 끝났으니 main에 합쳐주세요” 요청

### Review
다른 팀원이 코드를 확인

### Merge
검토가 끝난 코드를 main에 합치는 것

## 7-3. Branch 예시

```text
feature/vehicle-collect
feature/faq-collect
feature/mysql-load
feature/mongodb-load
fix/duplicate-handling
docs/brd-prd
```

## 7-4. Issue 제목 예시

```text
[FR-VEH-COLLECT-001] 자동차 데이터 수집 구현

[DR-FAQ-001] FAQ document 품질 규칙 구현

[NFR-OBS-001] Pipeline 실행 로그 구현
```

---

# 8. 오후 — 기술 설계 시작

**BRD/PRD가 어느 정도 합의된 다음** 기술적인 구조를 설계합니다.

## 8-1. 결정할 내용

- 자동차 Source Registry
- FAQ Source Registry
- Data Contract
- MySQL Table / Key / Index
- MongoDB Document / Index
- Pipeline Stage
- AWS 역할 / 배치
- `.env` / Secret 분리
- 로그 구조

---

## 8-2. Source Registry란?

사용할 데이터 Source 정보를 한 곳에 정리한 목록입니다.

예:

```yaml
vehicle:
  provider: 공공데이터포털
  type: API
  allowed: true

faq:
  provider: instructor-server
  type: HTML
  allowed_pages: 2
```

실제 키나 비밀번호는 여기에 적으면 안 됩니다.

---

## 8-3. Data Contract란?

수집된 데이터가 어떤 필드를 가져야 하는지 정한 **데이터 약속**입니다.

예:

```text
base_month
region
vehicle_type
registration_count
```

그리고:

```text
registration_count는 정수
registration_count >= 0
region은 null 금지
```

같은 규칙도 포함할 수 있습니다.

---

## 8-4. Index란?

DB에서 데이터를 더 빨리 찾기 위한 **검색용 목차**라고 생각하면 됩니다.

예를 들어 FAQ를 항상:

```text
company + category
```

로 조회한다면 MongoDB에서 이 두 필드에 복합 Index를 만드는 것을 검토할 수 있습니다.

---

# 9. Pipeline 전체 흐름

오늘 팀원이 머릿속에 동일하게 가지고 있어야 할 기본 흐름입니다.

```text
Source
↓
Raw
↓
Transform
↓
Validate
↓
Load
↓
Query
```

### Source
데이터 원본

### Raw
원본을 최대한 그대로 확보한 상태

### Transform
DB에서 쓰기 좋은 형태로 변환

### Validate
결측·중복·형식·값 범위를 검사

### Load
MySQL / MongoDB에 저장

### Query
저장 결과가 실제 조회되는지 확인

---

# 10. 오늘 종료 전 반드시 확인

오늘 퇴실 전에 최소한 아래 파일의 상태가 잡혀 있어야 합니다.

```text
docs/
├── Business_Requirements_Document.md
├── Product_Requirements_Document.md
├── Requirements_Traceability.md
├── Cost_Estimation.md
└── 00_index.md
```

---

# 11. Peer Review 체크리스트

마지막 15~20분은 다른 팀원이 확인합니다.

- BRD 목표가 측정 가능한가?
- 모든 Must Requirement에 AC가 있는가?
- owner가 비어 있지 않은가?
- 미래 Evidence가 `pass`로 되어 있지 않은가?
- orphan requirement가 없는가?
- Secret / Private Endpoint가 문서에 들어가지 않았는가?
- In Scope / Out of Scope가 명확한가?
- 각 팀원이 내일 할 일을 설명할 수 있는가?

---

# 12. orphan requirement란?

다른 요구와 연결되지 않은 **고아 요구사항**입니다.

예:

```text
NFR-SECRET-001
```

이라는 보안 요구는 있는데
왜 필요한지 BRD 목표와 연결되지 않았다면
추적이 끊긴 상태입니다.

목표는:

```text
orphan Must requirement = 0
```

입니다.

---

# 13. 4명 역할 예시

| 사람 | 오늘 주담당 |
|---|---|
| 1 | 자동차 Source + FR/DR + MySQL 초안 |
| 2 | FAQ Source + FR/DR + MongoDB 초안 |
| 3 | AWS/Pipeline + NFR + 운영/로그 |
| 4 | BRD/PRD 취합 + AC/Traceability/Review |

> **주의:** 주담당은 “혼자 결정한다”는 뜻이 아닙니다.  
> 특히 BRD 범위, Business Key, AC, DB 주요 구조는 팀원끼리 공유하고 합의합니다.

---

# 14. 오늘 작업 추천 순서

```text
1. 팀 공통 범위 합의
        ↓
2. Source 확인
        ↓
3. BRD 작성
        ↓
4. PRD 작성
        ↓
5. AC 작성
        ↓
6. Fixture 준비
        ↓
7. Traceability 연결
        ↓
8. Git Issue / Branch 계획
        ↓
9. 기술 설계 초안
        ↓
10. Peer Review
        ↓
11. Day 22 Handoff 준비
```

---

# 15. 오늘의 완료 기준

오늘 가장 중요한 것은 많은 코드를 만드는 것이 아닙니다.

**내일부터 네 명이 각자 구현에 들어가더라도 서로 다른 프로젝트를 만들지 않는 상태**를 만드는 것입니다.

팀원 모두가 아래 문장을 설명할 수 있으면 오늘 작업이 잘 된 것입니다.

> 우리는 어떤 Source에서 어떤 데이터를 가져와 어떤 규칙으로 검증하고 어디에 저장할 것이며,  
> 각각의 기능이 어떤 요구사항에 연결되고 무엇을 확인해야 완료인지 알고 있다.
