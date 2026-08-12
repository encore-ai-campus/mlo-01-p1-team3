"""통계누리 자동차등록대수현황 수집 패키지."""

from .collector import DailyCollector, run

__all__ = ["DailyCollector", "run"]
