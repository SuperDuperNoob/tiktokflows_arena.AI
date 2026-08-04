"""
pytest fixtures. Points the machine at a throwaway temp HOME + config so the
test suite never touches real content/, logs/ or config.yaml.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

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
    "proxy:\n  endpoint: ''\n  strict_mode: true\n  geo_check: true\n",
    encoding="utf-8")
os.environ["TIKTOK_MACHINE_CONFIG"] = str(CONFIG_PATH)

import lib  # noqa: E402
lib._CFG = None  # force reload of the temp config


@pytest.fixture
def reset_config():
    """Reload lib config from the temp config.yaml after a test mutates it."""
    def _reset():
        lib._CFG = None
        lib.load_config()
    yield _reset
    lib._CFG = None


def make_dirs(*names: str) -> dict[str, Path]:
    """Create temp subdirs under TMP_HOME and return {name: path}."""
    out = {}
    for n in names:
        p = TMP_HOME / n
        p.mkdir(parents=True, exist_ok=True)
        out[n] = p
    return out
