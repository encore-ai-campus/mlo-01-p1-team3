# MLO 1기 1차 프로젝트

## 1. 팀 소개

### 팀명
- 팀명: `MLO-01-03`

### 멤버
| 이름 | 역할 | GitHub |
|---|---|---|
| 김남동 | 팀장 | [@rlaskaehd](https://github.com/rlaskaehd) |
| 신성민 | 팀원 | [@gururr-lab](https://github.com/gururr-lab) |
| 이인건 | 팀원 | [@2eelogan](https://github.com/2eelogan) |
| 이재원 | 팀원 | [@vvjeffvv3](https://github.com/vvjeffvv3) |

## 2. 프로젝트 개요

### 프로젝트 명
- `중고 자동차 영업·고객지원 데이터 통합 솔루션`

### 프로젝트 소개

본 프로젝트는 전국 판매망을 운영하는 중고 자동차 판매사를 가상의 고객사로 설정하고, 시장 데이터·중고차 매물 데이터·고객지원 데이터를 통합적으로 수집·관리·제공하는 데이터 솔루션을 구축하는 프로젝트이다.

### 프로젝트 필요성(배경)

시장 정보, 중고차 매물, 고객 FAQ가 서로 다른 출처와 방식으로 관리되어 담당자가 필요한 데이터를 개별적으로 확인하고 가공해야 한다. 이로 인해 데이터 탐색과 활용에 불필요한 시간이 소요되며, 부서별로 필요한 정보를 일관된 기준으로 활용하기 어렵다. 따라서 데이터별 특성에 맞는 수집·정제·검증·저장 체계를 구축하고, 업무에 필요한 데이터를 효율적으로 조회할 수 있는 통합 환경이 필요하다.

### 프로젝트 목표
- 영업 담당자의 시장 및 매물 정보 탐색 시간을 단축한다.
- 지역별 시장 현황을 기반으로 영업 및 차량 확보 전략 수립을 지원한다.
- 현재 보유 매물에 대한 조건별 조회와 비교를 지원한다.
- 고객지원 담당자의 FAQ 탐색 효율성을 높인다.
- 데이터 갱신 상태를 체계적으로 확인할 수 있도록 한다.
- 서로 다른 데이터 소스를 일관된 관리 체계 안에서 활용할 수 있도록 한다.

## 3. 기술 스택

| 구분 | 기술 |
|---|---|
| Language | Python |
| Data | MySQL, MongoDB |
| Collaboration | GitHub |
| Cloud | AWS |

## 4. WBS

- [1일차 상세 가이드](docs/1일차_상세가이드.md)
- [회의록](docs/Minutes/2026-08-11_MEETING_NOTES.md)
- 세부 WBS는 추가 예정

## 5. 요구사항 명세서

- [비즈니스 시나리오](docs/business-scenario.md)
- [Business Requirements Document](docs/Business_Requirements_Document.md)
- [Product Requirements Document](docs/Product_Requirements_Document.md)
- [요구사항 추적성](docs/requirements-traceability.md)
- [Data Specification](docs/Data%20Specification.md)
- [비용 산정](docs/17_비용_산정.md), [비용 산정 요약](docs/비용산정2.md)

## 6. ERD

- 추가 예정

## 7. 주요 프로시저

- 추가 예정

## 8. 수행결과(테스트/시연 페이지)

- 추가 예정

## 9. 한 줄 회고

| 이름 | 회고 |
|---|---|
| 김남동 | 한 줄 회고를 작성하세요. |
| 신성민 | 한 줄 회고를 작성하세요. |
| 이인건 | 한 줄 회고를 작성하세요. |
| 이재원 | 한 줄 회고를 작성하세요. |

## 10. 저장소 구조

```text
.
├── docs/       # 프로젝트 문서와 회의록
├── samples/    # 자동차등록현황보고 샘플 CSV
└── notebooks/  # Jupyter 노트북
```
