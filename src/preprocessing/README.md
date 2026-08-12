# preprocessing

원본 차량 JSON을 `cars` 테이블 행으로 정규화한다. 네트워크와 DB 접근은 포함하지 않는다.

- `value_from()`: 중첩 객체의 후보 필드 값을 선택
- `normalize_date()`: ISO 문자열을 날짜 문자열로 변환
- `normalize_car()`: 초기 차량 객체와 증분 이벤트 `payload`를 동일한 cars 입력 구조로 변환
