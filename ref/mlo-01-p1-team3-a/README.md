# 중고차 데이터 통합 솔루션 MVP

3일 안에 검증 가능한 **수집·전처리·저장·운영 모니터링 MVP**를 구축하기 위한 프로젝트 문서 저장소입니다.

## MVP 한 줄 정의

고정된 세 가지 데이터 수집 작업을 하나의 Python 백엔드에서 실행하고, FAQ는 MongoDB에 Upsert하며 정형 데이터는 SQL에 Upsert하고, 전체 처리 상태와 오류를 Python Dashboard 및 Discord로 확인합니다.

## 고정 기술 스택

| 영역 | 기술 |
|---|---|
| 애플리케이션·파이프라인·Dashboard | Python |
| 스케줄·배포·헬스체크 | Shell Script |
| 정형 데이터·운영 로그 | SQL |
| 비정형 FAQ 데이터 | MongoDB |
| 인프라·네트워크 | AWS |

## AWS MVP 구성

| 호스트 | 수량 | 역할 | 접근 |
|---|---:|---|---|
| Bastion | 1 | 운영자 SSH 진입점, 포트 포워딩 | Public |
| Backend | 1 | 수집·전처리·적재·로그·Dashboard·Discord 알림 | Private, Bastion 경유 |
| SQL | 1 | 자동차등록현황보고·중고차·실행 이력·애플리케이션 로그 | Private, Backend/Bastion 경유 |
| MongoDB | 1 | FAQ Document 저장 | Private, Backend/Bastion 경유 |

SQL은 이후 Primary–Replica(master–slave) 구조로 확장할 수 있게, MongoDB는 이후 3개 분산 서버와 Replica Set 투표/선출 구조로 확장할 수 있게 설계합니다. MVP에서 실제 복제와 자동 Failover를 구현하지는 않습니다.

## 데이터 Pipeline

| 데이터 | Source | 실행 | 전처리 | 저장 |
|---|---|---|---|---|
| FAQ | `http://192.168.0.51:4000/` 크롤링 | 매일 09:00 (KST) | 비정형 → MongoDB Document | MongoDB Upsert |
| 중고차 | `http://192.168.0.51:4000/` API | 1초마다 | 정형 → 관계형 SQL 준비 계약 | `vehicle_brands`·`vehicle_models`·`vehicle_locations`·`vehicle_dealers`·`vehicle_business_areas` + `vehicle_listings`, 최초 Insert 후 증분 Upsert |
| 자동차등록현황보고 | 등록현황보고 API | 매일 1회 | `formList`의 각 지표를 월·시도명·시군구·차량구분·용도구분·수량 SQL Row로 분해 | 실행당 1회 호출, 일일 3,000회 초과 방지 |

중고차 Worker는 1초에 한 번씩 순차 호출하고 한 번에 최대 500건을 처리합니다. 초기 데이터가 1만건이면 최대 20회 호출을 1초 간격으로 수행한 뒤, 마지막 성공 Checkpoint 이후의 신규·변경 데이터만 증분 수집합니다.

모든 작업은 다음 논리 레이어를 거칩니다.

```text
Collect → Preprocess → Validate → Load
                           ├─ SQL
                           └─ MongoDB
```

실제 Python 코드는 단계별 폴더로 분리되어 있습니다. `collection/`은 외부 Source와 fixture만 담당하고, `preprocessing/`은 Raw 계약을 중고차 관계형 준비 계약·등록현황 정규화 Row·FAQ Document로 변환하며, `loading/`은 DB·JSONL·checkpoint·quota 정책을 담당합니다. `pipelines/`만 세 단계를 조합합니다. 단계 간 전달은 [`common/contracts.py`](src/common/contracts.py)의 `CollectionEnvelope`와 `PreparedBatch`를 사용합니다.

```text
src/
├── common/         # config, contracts, log, SQL 변환
├── collection/     # Source adapters
├── preprocessing/  # 순수 변환·검증
├── loading/        # SQL/MongoDB/JSONL·상태
└── pipelines/      # 실행 진입점
```

로컬 fixture 실행 예시는 다음과 같습니다.

```bash
python src/pipelines/faq.py --fixture tests/fixtures/faq.html --sink json
python src/pipelines/usedcar.py --mode initial --fixture tests/fixtures/usedcar_initial.json
python src/pipelines/registration.py --fixture tests/fixtures/registration.json --period 2026-06
```

## 문서 안내

0. [Implementation Plan](docs/00_implementation.md)
1. [비즈니스 시나리오](docs/01_Business_Scenario.md)
2. [BRD](docs/02_Business_Requirements_Document.md)
3. [PRD](docs/03_Product_Requirements_Document.md)
4. [요구사항 추적성](docs/04_requirements-traceability.md)
5. [데이터 명세](docs/05_Data%20Specification.md)
6. [Architecture](docs/06_architecture.md)
7. [Source Registry](docs/07_source-registry.md)
8. [Project Plan](docs/08_project-plan.md)
9. [Requirements Change Log](docs/09_change-log.md)
10. [Requirements Review Evidence](docs/10_requirements-review.md)
11. [GitHub Workflow](docs/90_GitHub_workflow_strategy.md)

문서 기준은 BRD의 Business Need·Objective·Scope, PRD의 User Need·Requirement Catalog·AC, Traceability의 BRD→PRD→AC→Evidence 연결을 사용합니다. 현재 세 수집·전처리 bounded entrypoint와 SQL/MongoDB migrations, `.env` 기반 로컬 DB 적재까지 검증했으며, 실시간 Source·운영 DB·Dashboard·Discord·systemd는 별도 서버 검증 범위입니다. 실제 구현 순서·로컬 검증·Amazon Linux 2023 배포 기준은 [Implementation Plan](docs/00_implementation.md)에 정리합니다.

`ref/`의 자동차등록현황 관련 Python 파일은 API 동작과 `form_id=5498`, `style_num=2` 계약을 확인하기 위한 참고 자료입니다. 최종 MVP의 저장 대상은 CSV가 아니라 SQL이며, 참고 코드의 파일 출력 방식은 제품 요구사항이 아닙니다.

## 3일 완료 기준

- Day 1: AWS 네트워크·네 대 호스트·DB·Source 연결 확인, SQL/MongoDB 스키마와 공통 실행 구조 확정
- Day 2: FAQ·중고차·자동차등록현황보고 수집/전처리/적재와 로직별 로그 구현
- Day 3: Python Dashboard, Discord 오류 알림, 스케줄·재실행·통합 검증 완료

## 착수 전 외부 선행조건

- AWS Backend에서 `192.168.0.51:4000`으로 연결되는 네트워크 경로가 있어야 합니다.
- 중고차 API가 1초당 1회 호출, 1회 500건, 증분 기준값(Sequence·수정시각·Cursor 중 하나)을 지원해야 합니다.
- 자동차등록현황보고 API 인증키와 일일 3,000회 한도 정책을 확인해야 합니다.
- 운영용 Discord Webhook URL을 제공해야 합니다.
- AWS 운영 계정, VPC 및 운영자 접속 허용 IP를 확인해야 합니다.
