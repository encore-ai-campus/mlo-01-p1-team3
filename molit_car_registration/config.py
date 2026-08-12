"""수집기 설정과 환경변수 처리."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_URL = "https://stat.molit.go.kr"
OPEN_API_URL = f"{BASE_URL}/portal/openapi/service/rest/getList.do"
SOURCE_PAGE = f"{BASE_URL}/portal/cate/statView.do?hRsId=58&hFormId=5498"
FORM_ID = 5498
STYLE_NUM = 2
DEFAULT_STORE_NAME = "자동차등록대수현황_시도별_누적.csv"
DEFAULT_STATE_NAME = "자동차등록대수현황_시도별_누적_상태.json"


@dataclass(frozen=True)
class CollectorConfig:
    """API와 누적 파일에 필요한 실행 설정."""

    api_key: str
    output_dir: Path
    insecure: bool = False
    max_lookback: int = 24
    store_name: str = DEFAULT_STORE_NAME
    state_name: str = DEFAULT_STATE_NAME

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("MOLIT_API_KEY가 비어 있습니다.")
        if self.max_lookback < 0:
            raise ValueError("max_lookback은 0 이상이어야 합니다.")


def api_key_from_environment() -> str:
    return os.environ.get("MOLIT_API_KEY", "").strip()
