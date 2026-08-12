"""자동차등록 파이프라인의 유일한 환경설정 진입점."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional


def _env(values: Mapping[str, str], name: str, default: str = "") -> str:
    return values.get(name, default).strip()


def _positive_int(values: Mapping[str, str], name: str, default: int) -> int:
    try:
        result = int(_env(values, name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if result <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return result


@dataclass(frozen=True)
class Settings:
    registration_api_url: str
    registration_api_key: Optional[str]
    registration_source_page: str
    registration_form_id: int
    registration_style_num: int
    output_dir: Path
    registration_state_path: Path
    log_path: Path
    registration_daily_quota: int
    timeout_seconds: int
    user_agent: str
    time_zone: str = "Asia/Seoul"
    sql_host: str = ""
    sql_port: int = 3306
    sql_database: str = ""
    sql_user: Optional[str] = None
    sql_password: Optional[str] = None

    @classmethod
    def from_env(cls, values: Optional[Mapping[str, str]] = None) -> "Settings":
        env = values if values is not None else os.environ
        output_dir = Path(_env(env, "OUTPUT_DIR", "output"))
        api_key = _env(env, "REGISTRATION_API_KEY") or _env(env, "MOLIT_API_KEY") or None
        return cls(
            registration_api_url=_env(
                env,
                "REGISTRATION_API_URL",
                "https://stat.molit.go.kr/portal/openapi/service/rest/getList.do",
            ),
            registration_api_key=api_key,
            registration_source_page=_env(
                env,
                "REGISTRATION_SOURCE_PAGE",
                "https://stat.molit.go.kr/portal/cate/statView.do?hRsId=58&hFormId=5498",
            ),
            registration_form_id=_positive_int(env, "REGISTRATION_FORM_ID", 5498),
            registration_style_num=_positive_int(env, "REGISTRATION_STYLE_NUM", 2),
            output_dir=output_dir,
            registration_state_path=Path(
                _env(env, "REGISTRATION_STATE_PATH", str(output_dir / "registration_state.json"))
            ),
            log_path=Path(_env(env, "LOG_PATH", str(output_dir / "jsonl"))),
            registration_daily_quota=_positive_int(env, "REGISTRATION_DAILY_QUOTA", 3000),
            timeout_seconds=_positive_int(env, "HTTP_TIMEOUT_SECONDS", 60),
            user_agent=_env(env, "USER_AGENT", "molit-car-registration/1.0"),
            time_zone=_env(env, "TIMEZONE", "Asia/Seoul"),
            sql_host=_env(env, "SQL_HOST"),
            sql_port=_positive_int(env, "SQL_PORT", 3306),
            sql_database=_env(env, "SQL_DATABASE"),
            sql_user=_env(env, "SQL_USER") or None,
            sql_password=_env(env, "SQL_PASSWORD") or None,
        )


def settings_from_env() -> Settings:
    return Settings.from_env()
