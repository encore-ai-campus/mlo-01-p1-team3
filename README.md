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
- `자동차 제조사 영업·고객지원 데이터 통합 솔루션`

### 프로젝트 소개
- 본 프로젝트는 `엔코아 AI Ready 데이터 엔지니어링 1기` 1차 프로젝트로써 특정 데이터를 수집하여 솔루션을 제공하는 것을 목적으로 합니다.

### 프로젝트 필요성(배경)
- 본 프로젝트는 서로 다른 형태와 출처를 가진 시장 데이터와 고객지원 데이터를 각각의 특성에 맞게 수집·정제·검증·저장하고, 각 부서에서 필요한 정보를 효율적으로 조회할 수 있는 데이터 통합 환경을 구축하는 것을 목적으로 한다.

### 프로젝트 목표
- 외부 자동차 등록 데이터를 정기적으로 수집하여 지역별 자동차 시장 현황을 조회할 수 있는 환경을 구축한다.
- 여러 제조사의 FAQ 데이터를 수집하여 카테고리별 고객 문의 정보를 효율적으로 조회할 수 있도록 한다.
- 서로 다른 데이터 소스를 공통적인 데이터 처리 흐름을 통해 관리한다.
- 수집된 데이터의 형식 및 필수 값 등을 검증하여 데이터 품질을 확보한다.
- 데이터 특성에 따라 적절한 데이터베이스에 저장한다.
- 영업팀, 고객지원팀, 운영팀이 각자의 업무 목적에 맞게 데이터를 조회할 수 있도록 한다.
- 데이터 갱신 결과와 오류 발생 여부를 기록하여 운영 상태를 추적할 수 있도록 한다.

## 3. 기술 스택

| 구분 | 기술 |
|---|---|
| Language | Python |
| Data | MySQL, MongoDB |
| Collaboration | GitHub |

## 4. WBS

- 추가 예정

## 5. 요구사항 명세서

- 추가 예정

## 6. ERD

- 추가 예정

## 7. 주요 프로시저

- 추가 예정

## 8. 수행결과(테스트/시연 페이지)

- 추가 예정

## 9. 데이터 수집 파이프라인 모듈화

기존 단일 스크립트의 수집, 데이터 정규화, DB 적재 책임을 `src/`의 단계별 패키지로 분리했습니다. 각 단계는 정해진 입력·출력 계약만 공유하며, 실제 실행 조합은 `pipelines/`에서만 수행합니다.

```text
collection → preprocessing → loading
                  ↑
             pipelines (실행 조합)
```

| 경로 | 책임 |
|---|---|
| `src/common/` | 환경변수 설정, 공통 계약, 구조화 로그, SQL 값 변환 |
| `src/collection/` | AutoData API/FAQ HTML 수집, 페이지·응답 검증, 재시도 |
| `src/preprocessing/` | 원천 레코드 검증·정규화, 관계형 중고차 aggregate 및 FAQ document 생성 |
| `src/loading/` | MySQL/MongoDB Upsert, transaction, checkpoint 관리 |
| `src/pipelines/` | Collect → Preprocess → Validate → Load orchestration |

실행 파일은 기존 목적을 유지하되 orchestration만 호출하는 얇은 진입점입니다.

| 실행 파일 | 동작 |
|---|---|
| `src/load_cars_initial.py` | 중고차 초기 데이터를 MySQL에 적재합니다. 기본 설정은 500건 × 20배치로 최대 10,000건입니다. |
| `src/update_cars_incremental.py` | checkpoint의 `after_seq`부터 변경분을 MySQL에 Upsert합니다. 기본 실행 주기는 5분이며 `--once`로 단발 실행할 수 있습니다. |
| `src/load_faqs_mongodb.py` | FAQ를 수집하여 `faq_id` 기준으로 MongoDB에 Upsert합니다. 기본 실행 주기는 5분이며 `--once`를 지원합니다. |

필수 환경변수는 `.env` 또는 시스템 환경변수로 제공합니다. MySQL은 `SQL_HOST`, `SQL_PORT`, `SQL_DATABASE`, `SQL_USER`, `SQL_PASSWORD`(기존 `MYSQL_*` 사용자·비밀번호도 호환), MongoDB는 `MONGODB_URI` 또는 `MONGODB_HOST`, `MONGODB_PORT`, `MONGODB_DATABASE`, `MONGODB_FAQ_COLLECTION`을 사용합니다.

```powershell
cd C:\encore_first_project\src
python load_cars_initial.py
python update_cars_incremental.py --once
python load_faqs_mongodb.py --once
```

## 10. 한 줄 회고

| 이름 | 회고 |
|---|---|
| 김남동 | 한 줄 회고를 작성하세요. |
| 신성민 | 한 줄 회고를 작성하세요. |
| 이인건 | 한 줄 회고를 작성하세요. |
| 이재원 | 한 줄 회고를 작성하세요. |
