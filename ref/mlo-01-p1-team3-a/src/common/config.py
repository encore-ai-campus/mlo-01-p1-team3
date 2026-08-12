"""Environment-backed configuration shared by the one-shot scripts.

The production service injects values through systemd EnvironmentFile.  Local
execution may use a .env file, but this module deliberately implements the
small subset of dotenv parsing that is needed here so the collector can run on
Amazon Linux 2023 without requiring python-dotenv.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Mapping, Optional, Tuple
from urllib.parse import quote, urlsplit


def load_dotenv(path: Optional[Path] = None) -> None:
    """Load simple KEY=VALUE pairs without overriding process environment."""

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


def _env(env: Mapping[str, str], key: str, default: str = "") -> str:
    return env.get(key, default).strip()


def _optional_env(env: Mapping[str, str], *keys: str) -> Optional[str]:
    """Return an optional secret without converting an empty value to a password."""

    for key in keys:
        if key in env:
            value = env[key].strip()
            return value or None
    return None


def _parse_mysql_jdbc_url(value: str) -> Tuple[str, Optional[int], str]:
    """Extract host, port, and database from a JDBC URL.

    Credentials are intentionally not read from the URL.  They belong in
    ``SQL_USER``/``SQL_PASSWORD`` so the same application config works with a
    password-less local MySQL and a secret-backed production account.
    """

    if not value:
        return "", None, ""
    normalized = value.strip()
    if normalized.startswith("jdbc:"):
        normalized = normalized[5:]
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"mysql", "mariadb"} or not parsed.hostname:
        raise ValueError("SQL_JDBC_URL must be a mysql:// or mariadb:// URL")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("SQL_JDBC_URL contains an invalid port") from exc
    database = parsed.path.lstrip("/").split("/", 1)[0]
    return parsed.hostname, port, database


def _mongo_uri(
    explicit_uri: str,
    *,
    host: str,
    port: int,
    user: Optional[str],
    password: Optional[str],
    auth_source: str,
) -> str:
    """Use an explicit URI or build a local/production-safe URI from env parts."""

    if explicit_uri:
        return explicit_uri
    if password is not None and not user:
        raise ValueError("MONGODB_USER is required when MONGODB_PASSWORD is set")
    authority = host
    if ":" in host and not host.startswith("["):
        authority = f"[{host}]"
    authority = f"{authority}:{port}"
    if user:
        credentials = quote(user, safe="")
        if password is not None:
            credentials += f":{quote(password, safe='')}"
        authority = f"{credentials}@{authority}"
    query = f"?authSource={quote(auth_source, safe='')}" if user and auth_source else ""
    return f"mongodb://{authority}/{query}"


def _positive_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = _env(env, key, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc
    if value <= 0:
        raise ValueError(f"{key} must be greater than zero")
    return value


def _positive_float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = _env(env, key, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be a number") from exc
    if value <= 0:
        raise ValueError(f"{key} must be greater than zero")
    return value


def _csv(env: Mapping[str, str], key: str, default: str) -> Tuple[str, ...]:
    """Read a comma-separated setting without introducing a dotenv dependency."""

    value = _env(env, key, default)
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    """Runtime settings for a bounded, single collection cycle."""

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
    faq_max_pages: int = 100
    faq_interval_seconds: float = 1.0
    faq_license: str = "educational-sandbox-rewrite"
    faq_attribution: str = "AutoData Lab educational snapshot; official source URL retained"
    faq_state_path: Path = Path("output/faq_checkpoint.json")
    registration_api_url: str = "https://stat.molit.go.kr/portal/openapi/service/rest/getList.do"
    registration_api_key: Optional[str] = None
    registration_source_page: str = "https://stat.molit.go.kr/portal/cate/statView.do?hRsId=58&hFormId=5498"
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

        # Generic URL/key names belonged to the old MOLIT helper.  Do not let
        # those legacy names silently redirect this collector to another API.
        base_url = (
            _env(values, "USED_CAR_BASE_URL")
            or _env(values, "CAR_SOURCE_URL")
            or "http://192.168.0.51:4000"
        ).rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("BASE_URL must start with http:// or https://")

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
            _env(values, "USED_CAR_STATE_PATH", str(output_dir / "usedcar_checkpoint.json"))
        )
        log_path = Path(
            _env(values, "LOG_PATH", str(output_dir / "jsonl"))
        )
        faq_source_url = _env(values, "FAQ_SOURCE_URL") or f"{base_url}/faqs"
        faq_allowed_paths = _csv(values, "FAQ_ALLOWED_PATHS", "/faqs")
        if not faq_allowed_paths:
            raise ValueError("FAQ_ALLOWED_PATHS must contain at least one path")
        faq_interval_seconds = _positive_float(values, "FAQ_INTERVAL_SECONDS", 1.0)
        if faq_interval_seconds < 1.0:
            raise ValueError("FAQ_INTERVAL_SECONDS must be at least 1 second")
        registration_daily_quota = _positive_int(values, "REGISTRATION_DAILY_QUOTA", 3000)
        if registration_daily_quota > 3000:
            raise ValueError("REGISTRATION_DAILY_QUOTA must not exceed 3000")
        registration_state_path = Path(
            _env(values, "REGISTRATION_STATE_PATH", str(output_dir / "registration_state.json"))
        )
        faq_state_path = Path(
            _env(values, "FAQ_STATE_PATH", str(output_dir / "faq_checkpoint.json"))
        )

        jdbc_url = _env(values, "SQL_JDBC_URL") or _env(values, "MYSQL_JDBC_URL")
        jdbc_host, jdbc_port, jdbc_database = _parse_mysql_jdbc_url(jdbc_url)
        sql_host = _env(values, "SQL_HOST") or jdbc_host
        sql_port = _positive_int(values, "SQL_PORT", jdbc_port or 3306)
        sql_database = _env(values, "SQL_DATABASE") or jdbc_database or "sales_support_db"
        sql_user = _optional_env(values, "SQL_USER", "MYSQL_USER")
        sql_password = _optional_env(values, "SQL_PASSWORD", "MYSQL_PASSWORD")
        mongo_host = _env(values, "MONGODB_HOST", "localhost")
        mongo_port = _positive_int(values, "MONGODB_PORT", 27017)
        mongo_user = _optional_env(values, "MONGODB_USER", "MONGO_USER")
        mongo_password = _optional_env(values, "MONGODB_PASSWORD", "MONGO_PASSWORD")
        mongo_auth_source = _env(values, "MONGODB_AUTH_SOURCE", "admin")
        explicit_mongo_uri = _env(values, "MONGODB_URI") or _env(values, "MONGO_URI")

        return cls(
            base_url=base_url,
            api_key=_env(values, "USED_CAR_API_KEY") or _env(values, "AUTO_DATA_API_KEY") or None,
            output_dir=output_dir,
            state_path=state_path,
            log_path=log_path,
            batch_size=batch_size,
            initial_target=initial_target,
            max_batches=max_batches,
            interval_seconds=interval_seconds,
            timeout_seconds=_positive_float(values, "HTTP_TIMEOUT_SECONDS", 30.0),
            user_agent=_env(values, "USER_AGENT", "mlo-used-car-collector/0.1"),
            sql_host=sql_host,
            sql_port=sql_port,
            sql_database=sql_database,
            sql_user=sql_user,
            sql_password=sql_password,
            app_env=_env(values, "APP_ENV", "local"),
            time_zone=_env(values, "TIMEZONE", "Asia/Seoul"),
            faq_source_url=faq_source_url,
            faq_allowed_paths=faq_allowed_paths,
            faq_max_pages=_positive_int(values, "FAQ_MAX_PAGES", 100),
            faq_interval_seconds=faq_interval_seconds,
            faq_license=_env(values, "FAQ_LICENSE", "educational-sandbox-rewrite"),
            faq_attribution=_env(
                values,
                "FAQ_ATTRIBUTION",
                "AutoData Lab educational snapshot; official source URL retained",
            ),
            faq_state_path=faq_state_path,
            registration_api_url=_env(
                values,
                "REGISTRATION_API_URL",
                "https://stat.molit.go.kr/portal/openapi/service/rest/getList.do",
            ),
            registration_api_key=_env(values, "REGISTRATION_API_KEY")
            or _env(values, "MOLIT_API_KEY")
            or None,
            registration_source_page=_env(
                values,
                "REGISTRATION_SOURCE_PAGE",
                "https://stat.molit.go.kr/portal/cate/statView.do?hRsId=58&hFormId=5498",
            ),
            registration_form_id=_positive_int(values, "REGISTRATION_FORM_ID", 5498),
            registration_style_num=_positive_int(values, "REGISTRATION_STYLE_NUM", 2),
            registration_daily_quota=registration_daily_quota,
            registration_start_period=_env(values, "REGISTRATION_START_PERIOD"),
            registration_state_path=registration_state_path,
            mongo_uri=_mongo_uri(
                explicit_mongo_uri,
                host=mongo_host,
                port=mongo_port,
                user=mongo_user,
                password=mongo_password,
                auth_source=mongo_auth_source,
            ),
            mongo_host=mongo_host,
            mongo_port=mongo_port,
            mongo_user=mongo_user,
            mongo_password=mongo_password,
            mongo_auth_source=mongo_auth_source,
            mongo_database=_env(values, "MONGODB_DATABASE", "support_db"),
            mongo_collection=_env(values, "MONGODB_FAQ_COLLECTION", "faq"),
            mongo_server_selection_timeout_ms=_positive_int(
                values, "MONGODB_SERVER_SELECTION_TIMEOUT_MS", 5000
            ),
            sql_log_database=_env(values, "SQL_LOG_DATABASE", "application_logs"),
        )


def settings_from_env(dotenv_path: Optional[Path] = None) -> Settings:
    return Settings.from_env(dotenv_path=dotenv_path)
