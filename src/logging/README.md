# logging

파이프라인 실행 로그를 JSONL 한 줄 단위로 남기는 전용 모듈이다. 설정, 수집, 전처리, 적재 규칙은 포함하지 않는다.

| 파일 | 역할 |
| --- | --- |
| `logging_utils.py` | UTC 기반 JSONL 이벤트 기록과 비밀값 마스킹 |

## 사용

프로젝트 루트에서 실행하는 코드에서는 다음처럼 가져온다.

```python
from src.logging.logging_utils import JsonlLogger
```

`JsonlLogger.event()`는 `ts`, `level`, `event_name`, `message`, `run_id` 등의 구조화 필드를 JSONL 파일과 stderr에 기록한다. `api_key`, `password`, Bearer token, MongoDB URI, Slack/Discord webhook은 `[REDACTED]`로 마스킹한다.

## 경계

- `logging`은 표준 라이브러리 이름과 겹치므로 `from logging import ...`로 가져오지 않는다.
- 반드시 프로젝트 최상위 패키지 경로를 포함한 `from src.logging.logging_utils import ...` 형태를 사용한다.
- 어느 단계에도 직접 의존하지 않으며, 파일 기록만 수행한다.
