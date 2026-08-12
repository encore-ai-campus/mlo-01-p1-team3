"""기존 실행 명령을 유지하기 위한 통계누리 수집기 실행 파일."""

from molit_car_registration.collector import DailyCollector, run
from molit_car_registration.cli import main

__all__ = ["DailyCollector", "main", "run"]


if __name__ == "__main__":
    raise SystemExit(main())
