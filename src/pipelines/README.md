# pipelines

수집 → 전처리 → 적재를 조합한다.

- `cars.py`: 초기 최대 10,000건 적재와 증분 1회 처리
- `faq.py`: FAQ 수집 후 MongoDB 적재 1회 처리

`cars.py`의 `run_incremental_once()`는 원본 증분 갱신의 한 번 실행 분량이고, 5분 반복은 `src/update_cars_incremental.py`가 담당한다.
