"""환경 변수와 프로젝트 경로를 한곳에서 관리한다."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


# ============================================================================
# CONFIGURATION START: 파이프라인 설정을 환경 변수에서 읽는다.
# ============================================================================


@dataclass(frozen=True)
class Settings:
    """Collector 실행에 필요한 환경 설정값이다."""

    base_url: str
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    mysql_replica_host: str
    mysql_replica_port: int
    mysql_monitor_user: str
    mysql_monitor_password: str
    mongo_uri: str
    mongo_database: str
    mongo_faq_collection: str
    request_timeout_seconds: int
    api_page_size: int
    api_max_pages: int
    project_dir: Path
    data_dir: Path
    raw_dir: Path
    rejected_dir: Path
    archive_dir: Path
    log_dir: Path

    @property
    def public_key_url(self) -> str:
        return f"{self.base_url}/api/v1/public-key"

    @property
    def cars_url(self) -> str:
        return f"{self.base_url}/api/v1/cars"

    @property
    def changes_url(self) -> str:
        return f"{self.base_url}/api/v1/changes"

    @property
    def faqs_url(self) -> str:
        return f"{self.base_url}/faqs"


def load_settings() -> Settings:
    """.env와 운영체제 환경 변수에서 설정을 읽고 기본 경로를 만든다."""
    project_dir = Path(__file__).resolve().parent
    data_dir = project_dir / "data"
    return Settings(
        base_url=os.getenv("BASE_URL", "http://192.168.0.51:4000").rstrip("/"),
        mysql_host=os.getenv("MYSQL_HOST", ""),
        mysql_port=int(os.getenv("MYSQL_PORT", "3306")),
        mysql_user=os.getenv("MYSQL_USER", ""),
        mysql_password=os.getenv("MYSQL_PASSWORD", ""),
        mysql_database=os.getenv("MYSQL_DATABASE", ""),
        mysql_replica_host=os.getenv("MYSQL_REPLICA_HOST", ""),
        mysql_replica_port=int(os.getenv("MYSQL_REPLICA_PORT", "3306")),
        mysql_monitor_user=os.getenv("MYSQL_MONITOR_USER", os.getenv("MYSQL_USER", "")),
        mysql_monitor_password=os.getenv("MYSQL_MONITOR_PASSWORD", os.getenv("MYSQL_PASSWORD", "")),
        mongo_uri=os.getenv("MONGO_URI", ""),
        mongo_database=os.getenv("MONGO_DATABASE", "car_data"),
        mongo_faq_collection=os.getenv("MONGO_FAQ_COLLECTION", "faqs"),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        api_page_size=int(os.getenv("API_PAGE_SIZE", "100")),
        api_max_pages=int(os.getenv("API_MAX_PAGES", "100")),
        project_dir=project_dir,
        data_dir=data_dir,
        raw_dir=data_dir / "raw",
        rejected_dir=data_dir / "rejected",
        archive_dir=data_dir / "archive",
        log_dir=project_dir / "logs",
    )


# ============================================================================
# CONFIGURATION END: 설정 로드 기능의 끝.
# ============================================================================
