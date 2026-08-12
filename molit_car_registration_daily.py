"""자동차등록현황보고 파이프라인의 호환 실행 진입점.

실제 구현은 조장님이 정의한 다음 단계별 구조에 있습니다.

    ref/mlo-01-p1-team3-a/src/
        collection/registration.py
        preprocessing/registration.py
        loading/registration.py
        pipelines/registration.py

이 파일은 기존 실행 명령을 유지하면서 canonical pipeline만 호출합니다.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = PROJECT_ROOT / "ref" / "mlo-01-p1-team3-a" / "src"
if not SOURCE_ROOT.exists():
    raise SystemExit(f"canonical source directory not found: {SOURCE_ROOT}")

sys.path.insert(0, str(SOURCE_ROOT))

from pipelines.registration import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
