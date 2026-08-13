"""Environment-backed configuration shared by every pipeline stage.

Local execution may use a small ``.env`` file; EC2/systemd can inject the
same variables directly.  No stage reads environment variables on its own.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Mapping, Optional, Tuple
from urllib.parse import quote, urlsplit


def load_dotenv(path: Optional[Path] = None) -> None:
    """Load simple ``KEY=VALUE`` pairs without overriding process settings."""

    dotenv_path = path or Path.cwd() / ".env"
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _env(values: Mapping[str, str], key: str, default: str = "") -> str:
    return str(values.get(key, default)).strip()


def _optional_env(values: Mapping[str, str], *keys: str) -> Optional[str]:
    for key in keys:
        if key in values:
            value = _env(values, key)
            # An empty preferred variable must not hide a populated legacy
            # alias while the environment names are being migrated.
            if value:
                return value
    return None


def _positive_int(values: Mapping[str, str], key: str, default: int) -> int:
    try:
        value = int(_env(values, key, str(default)))
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{key} must be greater than zero")
    return value


def _positive_float(values: Mapping[str, str], key: str, default: float) -> float:
    try:
        value = float(_env(values, key, str(default)))
    except ValueError as exc:
        raise ValueError(f"{key} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{key} must be greater than zero")
    return value


def _csv(values: Mapping[str, str], key: str, default: str) -> Tuple[str, ...]:
    return tuple(
        item.strip() for item in _env(values, key, default).split(",") if item.strip()
    )


def _parse_mysql_jdbc_url(value: str) -> tuple[str, Optional[int], str]:
    """Extract host/port/database only; credentials stay in SQL_* variables."""

    if not value:
        return "", None, ""
    normalized = value[5:] if value.startswith("jdbc:") else value
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"mysql", "mariadb"} or not parsed.hostname:
        raise ValueError("SQL_JDBC_URL must be a mysql:// or mariadb:// URL")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("SQL_JDBC_URL contains an invalid port") from exc
    return parsed.hostname, port, parsed.path.lstrip("/").split("/", 1)[0]


def _mongo_uri(
    explicit_uri: str,
    *,
    host: str,
    port: int,
    user: Optional[str],
    password: Optional[str],
    auth_source: str,
) -> str:
    if explicit_uri:
        return explicit_uri
    if password is not None and not user:
        raise ValueError("MONGODB_USER is required when MONGODB_PASSWORD is set")
    authority = f"[{host}]" if ":" in host and not host.startswith("[") else host
    authority = f"{authority}:{port}"
    if user:
        credentials = quote(user, safe="")
        if password is not None:
            credentials += f":{quote(password, safe='')}"
        authority = f"{credentials}@{authority}"
    query = f"?authSource={quote(auth_source, safe='')}" if user and auth_source else ""
    return f"mongodb://{authority}/{query}"


@dataclass(frozen=True)
class Settings:
    """All runtime configuration consumed by collection, loading, and pipelines."""

    base_url: str
    api_key: Optional[str]
    output_dir: Path
    state_path: Path
    log_path: Path
    batch_size: int
    initial_target: int
    max_batches: int
    interval_seconds: float
    timeout_seconds: float
    user_agent: str
    sql_host: str
    sql_port: int
    sql_database: str
    sql_user: Optional[str]
    sql_password: Optional[str]
    app_env: str = "local"
    time_zone: str = "Asia/Seoul"
    faq_source_url: str = ""
    faq_allowed_paths: Tuple[str, ...] = ("/faqs",)
    faq_max_pages: int = 2
    faq_max_questions_per_page: int = 500
    faq_interval_seconds: float = 1.0
    faq_license: str = "educational-sandbox-rewrite"
    faq_attribution: str = (
        "AutoData Lab educational snapshot; official source URL retained"
    )
    faq_state_path: Path = Path("output/faq_checkpoint.json")
    registration_api_url: str = (
        "https://stat.molit.go.kr/portal/openapi/service/rest/getList.do"
    )
    registration_api_key: Optional[str] = None
    registration_source_page: str = (
        "https://stat.molit.go.kr/portal/cate/statView.do?hRsId=58&hFormId=5498"
    )
    registration_form_id: int = 5498
    registration_style_num: int = 2
    registration_daily_quota: int = 3000
    registration_start_period: str = ""
    registration_state_path: Path = Path("output/registration_state.json")
    mongo_uri: str = "mongodb://localhost:27017/"
    mongo_host: str = "localhost"
    mongo_port: int = 27017
    mongo_user: Optional[str] = None
    mongo_password: Optional[str] = None
    mongo_auth_source: str = "admin"
    mongo_database: str = "support_db"
    mongo_collection: str = "faq"
    mongo_server_selection_timeout_ms: int = 5000
    sql_log_database: str = "application_logs"

    @classmethod
    def from_env(
        cls,
        env: Optional[Mapping[str, str]] = None,
        dotenv_path: Optional[Path] = None,
    ) -> "Settings":
        load_dotenv(dotenv_path)
        values: Mapping[str, str] = env if env is not None else os.environ

        base_url = (
            _env(values, "USED_CAR_BASE_URL")
            or _env(values, "CAR_SOURCE_URL")
            or "http://192.168.0.51:4000"
        ).rstrip("/")
        parsed_base = urlsplit(base_url)
        if parsed_base.scheme not in {"http", "https"} or not parsed_base.netloc:
            raise ValueError("USED_CAR_BASE_URL must be an absolute HTTP(S) URL")

        batch_size = _positive_int(values, "USED_CAR_BATCH_SIZE", 500)
        if batch_size > 500:
            raise ValueError("USED_CAR_BATCH_SIZE must not exceed 500")
        initial_target = _positive_int(values, "USED_CAR_INITIAL_TARGET", 10000)
        configured_max_batches = _env(values, "USED_CAR_MAX_BATCHES")
        max_batches = (
            int(configured_max_batches)
            if configured_max_batches
            else ceil(initial_target / batch_size)
        )
        if max_batches <= 0:
            raise ValueError("USED_CAR_MAX_BATCHES must be greater than zero")
        interval_seconds = _positive_float(values, "USED_CAR_INTERVAL_SECONDS", 1.0)
        if interval_seconds < 1.0:
            raise ValueError("USED_CAR_INTERVAL_SECONDS must be at least 1 second")

        output_dir = Path(_env(values, "OUTPUT_DIR", "output"))
        state_path = Path(
            _env(
                values,
                "USED_CAR_STATE_PATH",
                str(output_dir / "usedcar_checkpoint.json"),
            )
        )
        log_path = Path(_env(values, "LOG_PATH", str(output_dir / "jsonl")))
        faq_source_url = _env(values, "FAQ_SOURCE_URL") or f"{base_url}/faqs"
        faq_allowed_paths = _csv(values, "FAQ_ALLOWED_PATHS", "/faqs")
        if not faq_allowed_paths:
            raise ValueError("FAQ_ALLOWED_PATHS must contain at least one path")
        faq_interval_seconds = _positive_float(values, "FAQ_INTERVAL_SECONDS", 1.0)
        if faq_interval_seconds < 1.0:
            raise ValueError("FAQ_INTERVAL_SECONDS must be at least 1 second")
        faq_max_pages = _positive_int(values, "FAQ_MAX_PAGES", 2)
        if faq_max_pages > 2:
            raise ValueError("FAQ_MAX_PAGES must not exceed 2")
        faq_max_questions_per_page = _positive_int(
            values, "FAQ_MAX_QUESTIONS_PER_PAGE", 500
        )
        registration_quota = _positive_int(values, "REGISTRATION_DAILY_QUOTA", 3000)
        if registration_quota > 3000:
            raise ValueError("REGISTRATION_DAILY_QUOTA must not exceed 3000")

        explicit_sql_url = _env(values, "SQL_JDBC_URL") or _env(
            values, "MYSQL_JDBC_URL"
        )
        jdbc_host, jdbc_port, jdbc_database = _parse_mysql_jdbc_url(explicit_sql_url)
        sql_host = _env(values, "SQL_HOST") or jdbc_host
        sql_port = _positive_int(values, "SQL_PORT", jdbc_port or 3306)
        sql_database = (
            _env(values, "SQL_DATABASE") or jdbc_database or "sales_support_db"
        )
        sql_user = _optional_env(values, "SQL_USER", "MYSQL_USER")
        sql_password = _optional_env(values, "SQL_PASSWORD", "MYSQL_PASSWORD")
        mongo_host = _env(values, "MONGODB_HOST") or _env(
            values, "MONGO_HOST", "localhost"
        )
        mongo_port_raw = _env(values, "MONGODB_PORT") or _env(
            values, "MONGO_PORT", "27017"
        )
        try:
            mongo_port = int(mongo_port_raw)
        except ValueError as exc:
            raise ValueError("MONGODB_PORT must be an integer") from exc
        if mongo_port <= 0:
            raise ValueError("MONGODB_PORT must be greater than zero")
        mongo_user = _optional_env(values, "MONGODB_USER", "MONGO_USER")
        mongo_password = _optional_env(values, "MONGODB_PASSWORD", "MONGO_PASSWORD")
        mongo_auth_source = _env(values, "MONGODB_AUTH_SOURCE", "admin")
        explicit_mongo_uri = _env(values, "MONGODB_URI") or _env(values, "MONGO_URI")
        app_env = _env(values, "APP_ENV", "local").lower()
        mongo_uri = _mongo_uri(
            explicit_mongo_uri,
            host=mongo_host,
            port=mongo_port,
            user=mongo_user,
            password=mongo_password,
            auth_source=mongo_auth_source,
        )

        if app_env in {"production", "prod"}:
            # Production must not silently fall back to localhost or a
            # password-less account when a variable is missing.
            if not sql_host or not sql_user or not sql_password:
                raise ValueError(
                    "production requires SQL_HOST/SQL_JDBC_URL, SQL_USER, and SQL_PASSWORD"
                )
            if not explicit_mongo_uri:
                raise ValueError("production requires an explicit MONGODB_URI")
            parsed_mongo = urlsplit(mongo_uri)
            has_uri_credentials = bool(parsed_mongo.username and parsed_mongo.password)
            if not has_uri_credentials and not (mongo_user and mongo_password):
                raise ValueError(
                    "production requires MongoDB credentials in MONGODB_URI or MONGODB_USER/MONGODB_PASSWORD"
                )

        return cls(
            base_url=base_url,
            api_key=_optional_env(values, "USED_CAR_API_KEY", "AUTO_DATA_API_KEY"),
            output_dir=output_dir,
            state_path=state_path,
            log_path=log_path,
            batch_size=batch_size,
            initial_target=initial_target,
            max_batches=max_batches,
            interval_seconds=interval_seconds,
            timeout_seconds=_positive_float(values, "HTTP_TIMEOUT_SECONDS", 30.0),
            user_agent=_env(values, "USER_AGENT", "mlo-pipeline/1.0"),
            sql_host=sql_host,
            sql_port=sql_port,
            sql_database=sql_database,
            sql_user=sql_user,
            sql_password=sql_password,
            app_env=app_env,
            time_zone=_env(values, "TIMEZONE", "Asia/Seoul"),
            faq_source_url=faq_source_url,
            faq_allowed_paths=faq_allowed_paths,
            faq_max_pages=faq_max_pages,
            faq_max_questions_per_page=faq_max_questions_per_page,
            faq_interval_seconds=faq_interval_seconds,
            faq_license=_env(values, "FAQ_LICENSE", "educational-sandbox-rewrite"),
            faq_attribution=_env(
                values,
                "FAQ_ATTRIBUTION",
                "AutoData Lab educational snapshot; official source URL retained",
            ),
            faq_state_path=Path(
                _env(values, "FAQ_STATE_PATH", str(output_dir / "faq_checkpoint.json"))
            ),
            registration_api_url=_env(
                values,
                "REGISTRATION_API_URL",
                "https://stat.molit.go.kr/portal/openapi/service/rest/getList.do",
            ),
            registration_api_key=_optional_env(
                values, "REGISTRATION_API_KEY", "MOLIT_API_KEY"
            ),
            registration_source_page=_env(
                values,
                "REGISTRATION_SOURCE_PAGE",
                "https://stat.molit.go.kr/portal/cate/statView.do?hRsId=58&hFormId=5498",
            ),
            registration_form_id=_positive_int(values, "REGISTRATION_FORM_ID", 5498),
            registration_style_num=_positive_int(values, "REGISTRATION_STYLE_NUM", 2),
            registration_daily_quota=registration_quota,
            registration_start_period=_env(values, "REGISTRATION_START_PERIOD"),
            registration_state_path=Path(
                _env(
                    values,
                    "REGISTRATION_STATE_PATH",
                    str(output_dir / "registration_state.json"),
                )
            ),
            mongo_uri=mongo_uri,
            mongo_host=mongo_host,
            mongo_port=mongo_port,
            mongo_user=mongo_user,
            mongo_password=mongo_password,
            mongo_auth_source=mongo_auth_source,
            mongo_database=_env(values, "MONGODB_DATABASE")
            or _env(values, "MONGO_DATABASE", "support_db"),
            mongo_collection=_env(values, "MONGODB_FAQ_COLLECTION")
            or _env(values, "MONGO_COLLECTION", "faq"),
            mongo_server_selection_timeout_ms=_positive_int(
                values, "MONGODB_SERVER_SELECTION_TIMEOUT_MS", 5000
            ),
            sql_log_database=_env(values, "SQL_LOG_DATABASE", "application_logs"),
        )


def settings_from_env(dotenv_path: Optional[Path] = None) -> Settings:
    return Settings.from_env(dotenv_path=dotenv_path)


__all__ = ["Settings", "load_dotenv", "settings_from_env"]
