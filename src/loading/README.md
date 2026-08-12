# loading

원본 DB 스키마와 Upsert 정책을 담당한다.

- `mysql.py`: `business_areas`, `cars`, `crawl_logs` 생성 및 차량 적재
- `mysql.py`: 증분 checkpoint `get_last_seq()`와 `write_incremental_log()`
- `mongo.py`: FAQ 인덱스 및 `faq_id` 기준 MongoDB Upsert
