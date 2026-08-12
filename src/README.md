# `src` 모듈화 구조

원본 `python_crolling/`의 세 실행 파일은 수정하지 않았다. 해당 파일들의 함수와 실행 흐름을 아래 패키지로 역할만 나누어 이동했다.

```text
collection → preprocessing → loading
                    ↑
               pipelines
                    ↑
          실행 파일 3개
```

| 경로 | 원본에서 이동한 책임 |
|---|---|
| `common/` | `.env`, AutoData URL, MySQL/MongoDB 연결 설정 |
| `collection/` | API Key 조회·재시도 요청, FAQ HTML 요청·파싱 |
| `preprocessing/` | `normalize_car`, 날짜·중첩 JSON 값 정규화 |
| `loading/` | MySQL 테이블/Upsert/crawl log, MongoDB 인덱스/FAQ Upsert |
| `pipelines/` | 초기 1만 건 적재, 증분 1회 처리, FAQ 1회 처리 조합 |

## 실행 파일

| 파일 | 동작 |
|---|---|
| `load_cars_initial.py` | 최신 차량 최대 10,000건을 MySQL에 초기 적재 |
| `update_cars_incremental.py` | 마지막 `last_seq`부터 변경분을 MySQL에 5분마다 적재 |
| `load_faqs_mongodb.py` | FAQ를 MongoDB에 5분마다 Upsert |

세 작업을 한 파일에서 선택 실행하려면 `run_data_pipelines.py`를 사용한다.

```powershell
cd C:\encore_first_project\src
python run_data_pipelines.py initial
python run_data_pipelines.py incremental --once
python run_data_pipelines.py faq --once
```

`incremental`과 `faq`는 `--once`를 생략하면 기본 300초(5분) 주기로 반복 실행한다. `--interval-seconds`로 주기를 조정할 수 있다.

각 모듈의 코드 블록은 `시작`/`끝` 헤더로 구분했다. 특히 원본 `update_cars_incremental.py`에서 옮긴 부분은 `[update 코드 시작]`, `[update 코드 끝]` 헤더로 표시했다.
