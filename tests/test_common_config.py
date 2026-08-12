"""
===============================================================================
[TEST START] common.config unit tests

Purpose:
    Verify defaults, legacy environment aliases, and the supplied MongoDB
    Replica Set URI without contacting MongoDB or any external API.
===============================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for import_path in (str(ROOT), str(SRC)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from common.config import Settings  # noqa: E402


MONGODB_REPLICA_SET_URI = (
    "mongodb://10.0.10.30:27017,10.0.20.30:27017,10.0.10.31:27017/"
    "?replicaSet=rs0"
)


def test_common_config_defaults_aliases_and_replica_set_uri() -> None:
    """Check local defaults, legacy fallback, and complete URI preservation."""

    defaults = Settings.from_env(env={})
    assert defaults.base_url == "http://192.168.0.51:4000"
    assert defaults.sql_database == "sales_support_db"
    assert defaults.mongo_uri == "mongodb://localhost:27017/"
    assert defaults.sql_password is None

    settings = Settings.from_env(
        env={
            "USED_CAR_BASE_URL": "https://preferred.example/api",
            "SQL_USER": "",
            "MYSQL_USER": "legacy-user",
            "SQL_PASSWORD": "",
            "MYSQL_PASSWORD": "legacy-password",
            "MONGODB_URI": MONGODB_REPLICA_SET_URI,
        }
    )
    assert settings.base_url == "https://preferred.example/api"
    assert settings.sql_user == "legacy-user"
    assert settings.sql_password == "legacy-password"
    assert settings.mongo_uri == MONGODB_REPLICA_SET_URI


"""
===============================================================================
[TEST END] common.config unit tests
===============================================================================
"""
