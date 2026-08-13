"""Canonical command-line entry point for the project pipelines.

The individual modules under ``pipelines`` own their business rules and
``run_once`` workers.  This module only selects a pipeline, builds the shared
runtime settings, and presents one stable command-line contract.

The entry-point contract follows the current Day 22 requirements baseline:
fixture execution is the safe default, live execution is explicit, and a
single invocation has one top-level run ID.  The source-specific requirements
remain in ``pipelines.faq``, ``pipelines.registration``, and
``pipelines.usedcar``.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


SRC_ROOT = Path(__file__).resolve().parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from common.config import Settings, settings_from_env  # noqa: E402
from pipelines import faq, registration, usedcar  # noqa: E402


class MainError(ValueError):
    """A sanitized command-line or entry-point contract error."""

    def __init__(self, message: str, code: str = "entrypoint_error") -> None:
        super().__init__(message)
        self.code = code


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one project pipeline through the canonical src.main entry point."
    )
    parser.add_argument(
        "--pipeline",
        required=True,
        choices=("faq", "registration", "usedcar", "all"),
        help="Pipeline logic to run; all runs registration, usedcar, then FAQ.",
    )
    parser.add_argument(
        "--profile",
        choices=("fixture", "live"),
        default="fixture",
        help="Use a saved fixture by default; select live explicitly.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Explicitly document the one-shot execution contract.",
    )
    parser.add_argument("--fixture", type=Path, help="Fixture for the selected single pipeline.")
    parser.add_argument("--faq-fixture", type=Path)
    parser.add_argument("--registration-fixture", type=Path)
    parser.add_argument("--usedcar-fixture", type=Path)
    parser.add_argument("--sink", choices=("json", "mongo", "sql"))
    parser.add_argument("--faq-sink", choices=("json", "mongo"), default="json")
    parser.add_argument("--registration-sink", choices=("json", "sql"), default="json")
    parser.add_argument("--usedcar-sink", choices=("json", "sql"), default="json")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--mode", choices=("auto", "initial", "incremental"), default="auto")
    parser.add_argument("--period", "--stat-month", dest="period")
    return parser


def _settings_with_output(settings: Settings, output_dir: Optional[Path]) -> Settings:
    if output_dir is None:
        return settings
    return Settings(
        **{
            **settings.__dict__,
            "output_dir": output_dir,
            "log_path": output_dir / "jsonl",
            "state_path": output_dir / "usedcar_checkpoint.json",
            "faq_state_path": output_dir / "faq_checkpoint.json",
            "registration_state_path": output_dir / "registration_state.json",
        }
    )


def _fixture_for(args: argparse.Namespace, pipeline_name: str) -> Optional[Path]:
    if args.profile == "live":
        supplied = [args.fixture, args.faq_fixture, args.registration_fixture, args.usedcar_fixture]
        if any(item is not None for item in supplied):
            raise MainError("fixtures cannot be supplied with --profile live", "fixture_profile_conflict")
        return None

    if args.pipeline == "all":
        if args.fixture is not None:
            raise MainError("--fixture is only valid for one selected pipeline", "fixture_argument")
        selected = {
            "faq": args.faq_fixture,
            "registration": args.registration_fixture,
            "usedcar": args.usedcar_fixture,
        }[pipeline_name]
    else:
        extra = {
            "faq": args.faq_fixture,
            "registration": args.registration_fixture,
            "usedcar": args.usedcar_fixture,
        }[pipeline_name]
        if args.fixture is not None and extra is not None:
            raise MainError("use one of --fixture or the pipeline-specific fixture", "fixture_argument")
        selected = args.fixture or extra

    if selected is None:
        raise MainError(
            f"fixture is required for --profile fixture and pipeline={pipeline_name}",
            "fixture_required",
        )
    if not selected.is_file():
        raise MainError(f"fixture does not exist: {selected}", "fixture_error")
    return selected


def _run_one(
    pipeline_name: str,
    *,
    args: argparse.Namespace,
    settings: Settings,
    run_id: str,
) -> Dict[str, Any]:
    fixture = _fixture_for(args, pipeline_name)
    if pipeline_name == "faq":
        sink = args.sink or args.faq_sink
        if sink not in {"json", "mongo"}:
            raise MainError("FAQ supports only json or mongo sinks", "sink_argument")
        return faq.run_once(
            settings=settings,
            fixture=fixture,
            sink_name=sink,
            dry_run=args.dry_run,
            run_id=run_id,
        )
    if pipeline_name == "registration":
        sink = args.sink or args.registration_sink
        if sink not in {"json", "sql"}:
            raise MainError("registration supports only json or sql sinks", "sink_argument")
        return registration.run_once(
            settings=settings,
            fixture=fixture,
            sink_name=sink,
            dry_run=args.dry_run,
            period=args.period,
            run_id=run_id,
        )
    if pipeline_name == "usedcar":
        sink = args.sink or args.usedcar_sink
        if sink not in {"json", "sql"}:
            raise MainError("usedcar supports only json or sql sinks", "sink_argument")
        return usedcar.run_once(
            settings=settings,
            mode=args.mode,
            fixture=fixture,
            sink_name=sink,
            dry_run=args.dry_run,
            run_id=run_id,
        )
    raise MainError(f"unsupported pipeline: {pipeline_name}", "pipeline_argument")


def run(args: argparse.Namespace) -> Dict[str, Any]:
    if args.pipeline == "all" and args.sink is not None:
        raise MainError("use --faq-sink, --registration-sink, and --usedcar-sink with --pipeline all", "sink_argument")

    settings = _settings_with_output(settings_from_env(), args.output_dir)
    run_id = str(uuid.uuid4())
    pipeline_names = ("registration", "usedcar", "faq") if args.pipeline == "all" else (args.pipeline,)
    results: Dict[str, Any] = {}
    for pipeline_name in pipeline_names:
        results[pipeline_name] = _run_one(
            pipeline_name,
            args=args,
            settings=settings,
            run_id=run_id,
        )
    return {
        "status": "OK",
        "run_id": run_id,
        "pipeline": args.pipeline,
        "profile": args.profile,
        "results": results,
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        print(json.dumps(run(args), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "pipeline": args.pipeline,
                    "error_code": getattr(exc, "code", "pipeline_error"),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
