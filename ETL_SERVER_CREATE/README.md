# Collector / ETL Server

이 폴더는 Collector EC2에서 한 번 실행형으로 동작하는 데이터 파이프라인입니다. cron은 `main.py run`만 호출하며, DB 복제는 Collector가 아닌 MySQL·MongoDB가 각각 담당합니다.

## 전체 흐름

```text
cron
  ↓
python main.py run --source all --mode incremental
  ↓
cars: changes API / faqs: FAQ 페이지 수집
  ↓
data/raw 에 원본 JSON 저장
  ↓
transform + validation
  ├─ 실패 → data/rejected 및 MySQL etl_rejected_records 기록
  └─ 성공 → cars는 MySQL Primary A, FAQ는 MongoDB Replica Set
                 ↓                         ↓
              MySQL GTID/binlog          MongoDB Replica Set
                 ↓                         ↓
              MySQL Replica B          Secondary 노드들
```

## 파일별 기능

| 파일 | 기능 |
| --- | --- |
| `main.py` | CLI 진입점. 수집, raw 저장, 검증, 적재, 실행 이력을 순서대로 호출한다. |
| `collectors.py` | Cars API 초기/증분 수집, FAQ HTML 수집, 로컬 JSON 입력을 처리한다. |
| `transformers.py` | Cars 중첩 JSON을 MySQL `cars` 테이블 컬럼 구조로 정규화한다. |
| `validators.py` | Cars의 `id`·`listingNumber`, FAQ의 `faq_id`·`question`·`answer`를 검증한다. |
| `mysql_store.py` | **MySQL Primary A에만** 차량 UPSERT 및 실행 이력·검증 실패 기록을 수행한다. |
| `mongo_store.py` | Replica Set 전체 URI로 연결하여 현재 MongoDB Primary에 FAQ UPSERT한다. |
| `file_storage.py` | API 원본과 검증 실패 데이터를 날짜별 JSON 파일로 보관한다. |
| `monitor.py` | Monitoring EC2에서 실행 이력, MySQL Replica B, MongoDB Replica Set을 읽기 전용으로 점검한다. |
| `.env.example` | 운영 환경 변수 템플릿이다. 실제 비밀번호는 `.env`에만 저장한다. |
| `cron.example` | 5분마다 증분 실행하는 cron 등록 예시다. |

## 설치와 환경 설정

Collector EC2에서 이 폴더를 예를 들어 `/opt/data-pipeline`에 복사한 뒤 아래를 실행합니다.

```bash
cd /opt/data-pipeline
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

`.env`에는 실제 Private IP/DNS와 계정 정보를 입력합니다.

중요하게도 `MYSQL_HOST`는 **MySQL Primary A**만 넣습니다. Replica B에는 Collector가 직접 쓰지 않습니다. MySQL의 binlog/GTID 복제가 A의 변경을 B로 지속 반영합니다.

`MONGO_URI`는 아래 형태처럼 **모든 Replica Set 노드**와 `replicaSet` 이름을 포함해야 합니다. Primary 한 대의 IP만 고정하거나 `directConnection=true`를 넣으면 안 됩니다.

```text
mongodb://mongo-01:27017,mongo-02:27017,mongo-03:27017/car_data?replicaSet=rs0&authSource=admin&retryWrites=true&w=majority
```

## 실행 명령

```bash
# 운영: 증분 차량 + 최신 FAQ를 한 번 실행
python main.py run --source all --mode incremental

# 최초 차량 전체 적재 (최대 API_PAGE_SIZE × API_MAX_PAGES)
python main.py run --source cars --mode initial

# FAQ만 수집·적재
python main.py run --source faqs --mode incremental

# Bastion 경유로 받은 로컬 JSON 재처리: JSON이 cars 배열 또는 {"data": [...]}여야 함
python main.py run --source cars --mode initial --input /path/to/cars.json

# 로컬 FAQ JSON 재처리
python main.py run --source faqs --input /path/to/faqs.json

# Monitoring EC2: JSON 상태 출력. 하나라도 비정상이면 종료 코드 1
python monitor.py
```

`--input`을 쓰는 경우 `--source all`은 사용할 수 없습니다. 로컬 JSON은 초기 적재, 백필, 장애 복구에 사용하고, 일상 운영은 Collector가 API를 직접 호출합니다.

## 저장 데이터와 모니터링 기준

| 위치 | 내용 |
| --- | --- |
| `data/raw/YYYY-MM-DD/` | 변환 전 API/로컬 JSON 원본. 재처리와 장애 분석용이다. |
| `data/rejected/YYYY-MM-DD/` | 검증 실패 원본과 실패 사유다. |
| `logs/pipeline.log` | 애플리케이션 실행 로그다. |
| `etl_pipeline_runs` | source별 raw/valid/rejected/inserted/updated/failed 수와 `last_seq` 실행 이력이다. |
| `etl_rejected_records` | 검증 실패 건의 DB 감사 이력이다. |

Monitoring EC2는 `etl_pipeline_runs`의 마지막 결과를 확인하고, MySQL에서는 `SHOW REPLICA STATUS\G`, MongoDB에서는 `rs.status()`를 확인합니다. 다음은 알림 대상으로 권장합니다.

- 마지막 파이프라인 상태가 `FAILED`
- `rejected_count` 또는 `failed_count`가 0보다 큼
- MySQL `Replica_IO_Running` 또는 `Replica_SQL_Running`이 `Yes`가 아님
- MySQL replication lag가 운영 임계값 초과
- MongoDB Replica Set 멤버가 `PRIMARY`/`SECONDARY` 정상 상태가 아님

## cron 등록

`cron.example`의 `/opt/data-pipeline` 경로와 가상환경 경로를 맞춘 다음 `crontab -e`에 등록합니다. `flock -n`이 이미 실행 중인 작업이 있으면 새 실행을 건너뛰므로, API 지연 시 중복 적재 작업을 막습니다.

## 구현상 주의사항

- `etl_pipeline_runs.last_seq`는 **증분 이벤트의 적재 또는 rejected 기록까지 완료된 뒤**에만 성공 이력으로 남습니다.
- MySQL UPSERT와 마지막 체크포인트는 별도 트랜잭션 단위이며, 장애 재실행 시 UPSERT가 중복을 안전하게 흡수합니다.
- Replica는 백업이 아닙니다. 별도의 MySQL/MongoDB 백업 정책을 운영해야 합니다.
- `.env`는 절대 Git에 올리지 마십시오.
