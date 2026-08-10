"""
pytest fixtures. Points the machine at a throwaway temp HOME + config so the
test suite never touches real content/, logs/ or config.yaml.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Set TESTING=1 BEFORE any imports to skip config validation
os.environ["TESTING"] = "1"

# Import lib from scripts/ with a temp home BEFORE lib computes its paths.
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

TMP_HOME = Path(tempfile.mkdtemp(prefix="tiktok-machine-test-"))
os.environ["TIKTOK_MACHINE_HOME"] = str(TMP_HOME)
os.environ["TIKTOKFLOW_TZ"] = "Asia/Kuala_Lumpur"
# Ensure a valid config.yaml exists in the temp home for lib.config().
CONFIG_DIR = TMP_HOME / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = CONFIG_DIR / "config.yaml"
CONFIG_PATH.write_text(
    "logging:\n  db_path: logs/tiktok.db\n"
    "content:\n  raw_dir: content/raw\n  processed_dir: content/processed\n"
    "  failed_dir: content/failed\n  sounds_dir: sounds\n"
    "tiktok:\n  session_username: \"kumpul.shop\"\n"
    "analytics:\n  rival_handle: \"reski.reski700\"\n"
    "proxy:\n  endpoint: \"http://test:test@localhost:8080\"\n  strict_mode: true\n  geo_check: true\n"
    "telegram:\n  bot_token: \"test_token\"\n  allowed_user_id: 123456789\n"
    "ai:\n  base_url: \"https://test\"\n  api_key: \"test_key\"\n",
    encoding="utf-8")
os.environ["TIKTOK_MACHINE_CONFIG"] = str(CONFIG_PATH)


@pytest.fixture
def reset_config():
    """Reload lib config from the temp config.yaml after a test mutates it."""
    from services.infrastructure.config import Config
    def _reset():
        Config.reset_instance()
    yield _reset
    Config.reset_instance()


@pytest.fixture(autouse=True)
def fresh_db():
    """Start each test with a clean SQLite DB so tests never pollute each other."""
    from services.utils.paths import db_path
    db = db_path()
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db) + suffix)
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass
    yield


def make_dirs(*names: str) -> dict[str, Path]:
    """Create temp subdirs under TMP_HOME and return {name: path}."""
    out = {}
    for n in names:
        p = TMP_HOME / n
        p.mkdir(parents=True, exist_ok=True)
        out[n] = p
    return out
