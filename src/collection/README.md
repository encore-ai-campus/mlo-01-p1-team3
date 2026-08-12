# collection

외부 API·FAQ HTML 수집만 담당한다. DB 적재와 차량 정규화는 하지 않는다.

- `cars.py`: `get_api_key()`, `request_api()`
- `faq.py`: `get_faq_page()`, `get_text_or_default()`, `crawl_faqs()`

`cars.py`의 API Key 및 재시도 요청 블록은 원본 초기·증분 차량 코드에서 공통으로 사용하던 로직이다.
