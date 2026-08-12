"""명령줄 실행 진입점."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .api_client import MolitOpenApiError
from .collector import run
from .config import api_key_from_environment


def main() -> int:
    parser = argparse.ArgumentParser(
        description="통계누리 공식 Open API 자동차등록대수현황 시도별 일일 적재기"
    )
    parser.add_argument("--output-dir", default="outputs", help="결과 저장 폴더")
    parser.add_argument(
        "--max-lookback",
        type=int,
        default=24,
        help="최신 월 검색 시 현재 월부터 거슬러 올라갈 최대 개월 수",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="인증서 검증을 끕니다. TLS 오류가 있을 때만 사용하세요.",
    )
    args = parser.parse_args()
    if args.max_lookback < 0:
        parser.error("--max-lookback은 0 이상이어야 합니다.")

    api_key = api_key_from_environment()
    if not api_key:
        print(
            "실행 실패: MOLIT_API_KEY 환경변수에 통계누리 Open API 인증키를 설정하세요.",
            file=sys.stderr,
        )
        return 2

    try:
        store_path, state_path = run(
            Path(args.output_dir), api_key, args.insecure, args.max_lookback
        )
    except (MolitOpenApiError, RuntimeError, ValueError) as exc:
        print(f"통계누리 Open API 일일 적재 실패: {exc}", file=sys.stderr)
        return 1

    print(store_path)
    print(state_path)
    return 0
