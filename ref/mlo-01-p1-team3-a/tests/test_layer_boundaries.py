from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_stage_packages_do_not_depend_on_each_other_in_reverse() -> None:
    stage_modules = {
        stage: {
            path: _imported_modules(path)
            for path in sorted((SOURCE_ROOT / stage).glob("*.py"))
            if path.name != "__init__.py"
        }
        for stage in ("collection", "preprocessing", "loading")
    }
    for path, modules in stage_modules["collection"].items():
        assert not any(module.startswith("preprocessing") for module in modules), path
        assert not any(module.startswith("loading") for module in modules), path
    for path, modules in stage_modules["preprocessing"].items():
        assert not any(module.startswith("collection") for module in modules), path
        assert not any(module.startswith("loading") for module in modules), path
        assert "urllib.request" not in modules, path
    for path, modules in stage_modules["loading"].items():
        assert not any(module.startswith("collection") for module in modules), path
        assert not any(module.startswith("preprocessing") for module in modules), path
        assert "urllib.request" not in modules, path


def test_pipeline_modules_are_the_only_stage_composers() -> None:
    for path in sorted((SOURCE_ROOT / "pipelines").glob("*.py")):
        if path.name == "__init__.py":
            continue
        modules = _imported_modules(path)
        assert any(module.startswith("collection") for module in modules), path
        assert any(module.startswith("preprocessing") for module in modules), path
        assert any(module.startswith("loading") for module in modules), path
