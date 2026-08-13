# 문서 인덱스

중고 자동차 영업·고객지원 데이터 통합 솔루션 프로젝트의 문서 목록과 정본 관계를 정리한다.

## 1. 문서 목록

| 문서 | 역할 |
|---|---|
| [Project_Presentation.md](Project_Presentation.md) | 팀·시나리오·아키텍처·데이터 파이프라인·ERD·핵심 모듈 발표자료 |
| [Business_Scenario.md](Business_Scenario.md) | 프로젝트 비즈니스 시나리오와 활용 흐름 |
| [Business_Requirements_Document.md](Business_Requirements_Document.md) | 비즈니스 배경·목표·범위·비즈니스 요구사항 정본 |
| [Product_Requirements_Document.md](Product_Requirements_Document.md) | 제품 기능·데이터·운영 요구사항 및 Acceptance Criteria |
| [Requirements_Traceability.md](Requirements_Traceability.md) | 요구사항과 검증 근거의 추적성 |
| [Data_Specification.md](Data_Specification.md) | 데이터베이스와 데이터 구조 명세 |
| [Cost_Estimation.md](Cost_Estimation.md) | AWS 구성 기반 초기 구축비·월 운영비·데이터 공급비 |
| [AWS_DB_Infrastructure_PoC_Report_2026-08-11.md](AWS_DB_Infrastructure_PoC_Report_2026-08-11.md) | AWS 네트워크 및 DB 이중화 PoC 결과 |
| [Day1_Detailed_Guide.md](Day1_Detailed_Guide.md) | 1일차 협업·문서·검증 진행 가이드 |
| [GitHub_Workflow_Strategy.md](GitHub_Workflow_Strategy.md) | 브랜치·커밋·PR 협업 규칙 |
| [Meeting_Notes_2026-08-11.md](Minutes/Meeting_Notes_2026-08-11.md) | 프로젝트 회의 결정사항과 역할 분담 |

## 2. 정본 관계

```text
Business_Scenario
        ↓
Business_Requirements_Document
        ├── Product_Requirements_Document
        ├── Data_Specification
        ├── Cost_Estimation
        └── Requirements_Traceability
```

- 비즈니스 목적·범위·비용 요구사항은 `Business_Requirements_Document.md`를 정본으로 한다.
- 기능·데이터·운영 동작은 `Product_Requirements_Document.md`를 정본으로 한다.
- 비용 수치와 산정 가정은 `Cost_Estimation.md`를 정본으로 하며 BRD에는 핵심 결과를 요약한다.
- 구현·검증이 진행되면 `Requirements_Traceability.md`에서 요구사항과 근거를 연결한다.

## 3. 명명 규칙

- 문서 파일명은 영문 단어를 `_`로 연결한다.
- 문서명은 내용이 드러나는 PascalCase 형태를 사용한다. 예: `Business_Requirements_Document.md`
- 날짜가 필요한 회의록·리포트는 파일명 끝에 `YYYY-MM-DD`를 붙인다.
- 프로젝트 진입점인 `README.md`와 본 인덱스 파일명 `00_index.md`는 예외로 유지한다.
