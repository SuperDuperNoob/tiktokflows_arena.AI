"""End-to-End Integration Test Environment for TikTok Auto-Posting Machine.

Provides isolated test database, temporary storage, mocked external APIs,
and test media files for complete pipeline verification.
"""

import os
import sys
import tempfile
import shutil
import sqlite3
import hashlib
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Add project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVICES_DIR = PROJECT_ROOT / "services"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SERVICES_DIR))

# Enable testing mode
os.environ["TESTING"] = "1"


class TestEnvironment:
    """Manages isolated test environment for end-to-end pipeline testing."""
    
    def __init__(self):
        self.temp_dir: Optional[Path] = None
        self.db_path: Optional[Path] = None
        self.content_dirs: Dict[str, Path] = {}
        self.test_media: Dict[str, Path] = {}
        self.mocks: Dict[str, Any] = {}
        self._original_env = {}
        self._config_path: Optional[str] = None
        
    def setup(self) -> "TestEnvironment":
        """Create complete isolated test environment."""
        # Create temporary directory
        self.temp_dir = Path(tempfile.mkdtemp(prefix="tiktok_e2e_test_"))
        
        # Set config path BEFORE any imports that might trigger config loading
        self._config_path = str(self.temp_dir / "config" / "config.yaml")
        os.environ["TIKTOK_MACHINE_CONFIG"] = self._config_path
        os.environ["TESTING"] = "1"
        
        # Create directory structure FIRST (before config file)
        self._create_directory_structure()
        
        # Create config file BEFORE any imports that might trigger config loading
        self._create_config_file()
        
        # Create test database (will find config file now)
        self._create_test_database()
        
        # DEBUG: Check InfraConfig after initialization
        from services.infrastructure.config import get_config as infra_get_config
        cfg = infra_get_config()
        print(f"DEBUG after _create_test_database: infra config raw_dir={cfg.get('content', 'raw_dir')}, project_root={cfg._project_root}")
        
        # Monkey-patch path functions to use test paths
        import services.utils.paths as paths_module
        original_drive_root = paths_module.drive_root
        def test_drive_root():
            return self.content_dirs["drive_root"]
        paths_module.drive_root = test_drive_root
        
        original_processed_dir = paths_module.processed_dir
        def test_processed_dir():
            return self.content_dirs["processed"]
        paths_module.processed_dir = test_processed_dir
        
        original_queue_dir = paths_module.queue_dir
        def test_queue_dir():
            return self.content_dirs["queue"]
        paths_module.queue_dir = test_queue_dir
        
        original_failed_dir = paths_module.failed_dir
        def test_failed_dir():
            return self.content_dirs["failed"]
        paths_module.failed_dir = test_failed_dir
        
        original_sounds_dir = paths_module.sounds_dir
        def test_sounds_dir():
            return self.content_dirs["sounds"]
        paths_module.sounds_dir = test_sounds_dir
        
        original_db_path = paths_module.db_path
        def test_db_path():
            return self.db_path
        paths_module.db_path = test_db_path
        
        original_burn_jsonl = paths_module.burn_jsonl
        def test_burn_jsonl():
            return self.content_dirs["logs"] / "burn_log.jsonl"
        paths_module.burn_jsonl = test_burn_jsonl
        
        original_preset_txt = paths_module.preset_txt
        def test_preset_txt():
            return self.content_dirs["drive_root"] / "preset_txt.txt"
        paths_module.preset_txt = test_preset_txt
        
        original_product_txt = paths_module.product_txt
        def test_product_txt():
            return self.content_dirs["drive_root"] / "product_id.txt"
        paths_module.product_txt = test_product_txt
        
        # Create test media files
        self._create_test_media()
        
        # DEBUG: Check InfraConfig after media creation
        cfg = infra_get_config()
        print(f"DEBUG after _create_test_media: infra config raw_dir={cfg.get('content', 'raw_dir')}, project_root={cfg._project_root}")
        
        # Set up environment variables
        self._setup_env_vars()
        
        # Initialize mocks
        self._init_mocks()
        
        return self
    
    def _create_directory_structure(self):
        """Create all required content directories."""
        # The video service expects product folders under drive_root
        drive_root_dir = self.temp_dir / "content" / "raw"
        drive_root_dir.mkdir(parents=True, exist_ok=True)
        
        dirs = {
            "drive_root": drive_root_dir,
            "processed": self.temp_dir / "content" / "processed",
            "queue": self.temp_dir / "content" / "queue",
            "failed": self.temp_dir / "content" / "failed",
            "sidecars": self.temp_dir / "content" / "sidecars",
            "logs": self.temp_dir / "logs",
            "backups": self.temp_dir / "logs" / "backups",
            "sounds": self.temp_dir / "sounds",
        }
        
        for name, path in dirs.items():
            path.mkdir(parents=True, exist_ok=True)
            self.content_dirs[name] = path
        
        # Create product_id.txt and preset_text.txt
        self._create_config_files()
    
    def _create_config_files(self):
        """Create required config files."""
        # product_id.txt
        product_txt = self.content_dirs["drive_root"] / "product_id.txt"
        product_txt.write_text(
            "product_a|prod_a_001|Amazing Product A|Check out this amazing product!/Great deal\n"
            "product_b|prod_b_002|Product B Unboxing|Unboxing the new product B!/Unboxing\n"
            "product_c|prod_c_003|Failed Product|This will fail upload test\n"
            "product_d|prod_d_004|Compliance Test|Guaranteed results! Miracle cure! #scam\n"
        )
        
        # preset_text.txt
        preset_txt = self.content_dirs["drive_root"] / "preset_text.txt"
        preset_txt.write_text(
            "Amazing product demo! ---\n"
            "Check this out! ---\n"
            "Must have item! ---\n"
        )
        
        # Create sound files
        sounds_dir = self.content_dirs["sounds"]
        sounds_dir.mkdir(parents=True, exist_ok=True)
        (sounds_dir / "trending_sound_1.mp3").write_bytes(b"fake mp3" * 100)
        (sounds_dir / "trending_sound_2.mp3").write_bytes(b"fake mp3" * 100)
        (sounds_dir / "trending_sound_3.mp3").write_bytes(b"fake mp3" * 100)
    
    def _create_test_database(self):
        """Create isolated test database with schema."""
        self.db_path = self.temp_dir / "logs" / "test_tiktok.db"
        
        # Initialize services/infrastructure/config.py Config
        from services.infrastructure.config import Config as InfraConfig
        InfraConfig.reset_instance()
        InfraConfig.get_instance(Path(self._config_path) if self._config_path else None)
    
    def _create_test_media(self):
        """Create synthetic test video files in product folders."""
        # Create a minimal valid MP4 file (just header + minimal data)
        mp4_header = bytes([
            0x00, 0x00, 0x00, 0x18,  # size = 24
            0x66, 0x74, 0x79, 0x70,  # 'ftyp'
            0x69, 0x73, 0x6F, 0x6D,  # 'isom'
            0x00, 0x00, 0x02, 0x00,  # version
            0x69, 0x73, 0x6F, 0x6D,  # 'isom'
            0x6D, 0x70, 0x34, 0x31,  # 'mp41'
        ])
        
        # Create product folders and test videos
        test_videos = [
            ("product_a", "product_a_test.mp4", b"test content A" * 100000),  # ~1.4 MB
            ("product_b", "product_b_test.mp4", b"test content B" * 100000),  # ~1.4 MB
            ("product_c", "product_c_fail.mp4", b"fail content" * 100000),    # ~1.4 MB
            ("product_d", "product_d_compliance.mp4", b"compliance test" * 100000),  # ~1.4 MB
        ]
        
        for folder, filename, content in test_videos:
            folder_path = self.content_dirs["drive_root"] / folder
            folder_path.mkdir(parents=True, exist_ok=True)
            filepath = folder_path / filename
            filepath.write_bytes(mp4_header + content)
            self.test_media[filename] = filepath
        
        # Create sidecar files for each video
        self._create_sidecars()
    
    def _create_sidecars(self):
        """Create sidecar metadata files for test videos."""
        sidecar_data = {
            "product_a_test": {
                "product_id": "prod_a_001",
                "product_folder": "product_a",
                "title": "Amazing Product A Demo",
                "caption": "Check out this amazing product! #fyp #review",
                "hashtags": ["fyp", "review", "product"],
                "sound_name": "trending_sound_1",
                "trending_sound_id": "7123456789",
            },
            "product_b_test": {
                "product_id": "prod_b_002",
                "product_folder": "product_b",
                "title": "Product B Unboxing",
                "caption": "Unboxing the new product B! #unboxing #new",
                "hashtags": ["unboxing", "new", "tech"],
                "sound_name": "trending_sound_2",
                "trending_sound_id": "7123456790",
            },
            "product_c_fail": {
                "product_id": "prod_c_003",
                "product_folder": "product_c",
                "title": "Failed Product",
                "caption": "This will fail upload test",
                "hashtags": ["test", "fail"],
                "sound_name": "trending_sound_3",
                "trending_sound_id": "7123456791",
            },
            "product_d_compliance": {
                "product_id": "prod_d_004",
                "product_folder": "product_d",
                "title": "Compliance Test Product",
                "caption": "Guaranteed results! Miracle cure! #scam",
                "hashtags": ["guaranteed", "miracle"],
                "sound_name": "trending_sound_4",
                "trending_sound_id": "7123456792",
            },
        }
        
        for video_name, data in sidecar_data.items():
            # JSON sidecar
            json_path = self.content_dirs["sidecars"] / f"{video_name}.json"
            import json
            json_path.write_text(json.dumps(data, indent=2))
            
            # PID sidecar (legacy format)
            pid_path = self.content_dirs["sidecars"] / f"{video_name}.pid"
            pid_lines = [f"{k}: {v}" for k, v in data.items()]
            pid_path.write_text("\n".join(pid_lines))
    
    def _setup_env_vars(self):
        """Set up test environment variables."""
        # Save original values
        test_vars = {
            "TESTING": "1",
            "TIKTOK_MACHINE_CONFIG": self._config_path,
            "TIKTOK_PROXY": "http://test:test@127.0.0.1:8080",
            "OPENAI_API_KEY": "test-key",
            "APIFY_TOKEN": "test-token",
            "TELEGRAM_BOT_TOKEN": "test-token",
            "TELEGRAM_ALLOWED_USER_ID": "123456",
        }
        
        for key, value in test_vars.items():
            self._original_env[key] = os.environ.get(key)
            os.environ[key] = value
    
    def _create_config_file(self):
        """Create test config file."""
        config_dir = self.temp_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        config_content = f"""# Test configuration for end-to-end pipeline tests
telegram:
  bot_token: "test-token"
  allowed_user_id: 123456

proxy:
  endpoint: "http://test:test@127.0.0.1:8080"
  strict_mode: false
  geo_check: false

tiktok:
  session_username: "test_account"
  uploader_dir: "/fake/TiktokAutoUploader"

ai:
  enable_ai: false
  api_key: "test-key"
  model: "gpt-4o-mini"
  max_calls_per_day: 1

posting:
  daily_post_target: 7
  interval_minutes: 120
  quiet_hours_start: 22
  quiet_hours_end: 8

content:
  input_dir: "{self.content_dirs['drive_root']}"
  output_dir: "{self.content_dirs['processed']}"
  processed_dir: "{self.content_dirs['processed']}"
  queue_dir: "{self.content_dirs['queue']}"
  sidecar_dir: "{self.content_dirs['sidecars']}"
  min_duration: 3
  max_duration: 180
  required_hashtags: ["fyp"]
  banned_keywords: ["guaranteed", "miracle", "cure"]

encoding:
  crf: 28
  preset: "fast"

analytics:
  apify_token: "test-token"
  competitor_handles: ["comp1", "comp2"]
  scrape_schedule_hour: 3

google_drive:
  remote_name: "gdrive"
  sync_interval_hours: 6

logging:
  level: "DEBUG"
  file: "{self.content_dirs['logs']}/test_tiktok.log"
  db_path: "{self.db_path}"
  max_bytes: 1048576
  backup_count: 3
  json_format: false

timezone: "UTC"
"""
        config_dir = self.temp_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "config.yaml").write_text(config_content)
    
    def _init_mocks(self):
        """Initialize mock objects for external services."""
        # Mock TikTok adapter
        self.mocks["tiktok_adapter"] = MagicMock()
        self.mocks["tiktok_adapter"].upload_video = MagicMock(return_value=True)
        
        # Mock Telegram adapter
        self.mocks["telegram_adapter"] = MagicMock()
        self.mocks["telegram_adapter"].send_message = MagicMock(return_value=True)
        
        # Mock AI adapter
        self.mocks["ai_adapter"] = MagicMock()
        self.mocks["ai_adapter"].generate_growth_analysis = MagicMock(
            return_value={"analysis": "test analysis", "recommendations": []}
        )
        
        # Mock Storage adapter (rclone)
        self.mocks["storage_adapter"] = MagicMock()
        self.mocks["storage_adapter"].sync_from_drive = MagicMock(return_value=(True, {}))
        self.mocks["storage_adapter"].sync_to_drive = MagicMock(return_value=(True, {}))
        
        # Mock Proxy adapter
        self.mocks["proxy_adapter"] = MagicMock()
        self.mocks["proxy_adapter"].verify = MagicMock(return_value=(True, "Test proxy OK"))
        self.mocks["proxy_adapter"].get_exit_ip = MagicMock(return_value="1.2.3.4")
        
        # Mock FFmpeg adapter
        self.mocks["ffmpeg_adapter"] = MagicMock()
        self.mocks["ffmpeg_adapter"].process_video = MagicMock(return_value=True)
        self.mocks["ffmpeg_adapter"].get_video_info = MagicMock(return_value={
            "duration": 30.0,
            "width": 1080,
            "height": 1920,
            "fps": 30,
        })
        
        # Mock Skia adapter
        self.mocks["skia_adapter"] = MagicMock()
        self.mocks["skia_adapter"].render = MagicMock(return_value=True)
        print(f"DEBUG: Created skia_adapter mock with render={self.mocks['skia_adapter'].render}")
    
    def get_config_path(self) -> str:
        """Get path to test config."""
        return str(self.temp_dir / "config" / "config.yaml")
    
    def apply_mocks(self) -> List:
        """Apply all mocks and return patchers for cleanup."""
        patchers = []
        
        # Patch adapter imports in services
        from services.infrastructure import (
            tiktok_adapter, telegram_adapter, ai_adapter,
            rclone_adapter, proxy_adapter, ffmpeg_adapter, skia_adapter
        )
        
        patchers.append(patch.object(tiktok_adapter, "TikTokAdapter", return_value=self.mocks["tiktok_adapter"]))
        patchers.append(patch.object(telegram_adapter, "TelegramAdapter", return_value=self.mocks["telegram_adapter"]))
        patchers.append(patch.object(ai_adapter, "AIAdapter", return_value=self.mocks["ai_adapter"]))
        patchers.append(patch.object(rclone_adapter, "RcloneAdapter", return_value=self.mocks["storage_adapter"]))
        patchers.append(patch.object(proxy_adapter, "ProxyAdapter", return_value=self.mocks["proxy_adapter"]))
        patchers.append(patch.object(ffmpeg_adapter, "FFmpegAdapter", return_value=self.mocks["ffmpeg_adapter"]))
        patchers.append(patch.object(skia_adapter, "SkiaAdapter", return_value=self.mocks["skia_adapter"]))
        print(f"DEBUG: Patched skia_adapter.SkiaAdapter to return mock")
        
        # Patch proxy utility functions
        from services.utils import proxy
        patchers.append(patch.object(proxy, "check_proxy_exit", return_value=(True, "Test proxy OK")))
        # Note: get_proxy_exit_ip doesn't exist, check_proxy_exit returns the exit IP in detail
        
        # Patch subprocess.run for ffprobe calls
        import subprocess
        original_run = subprocess.run
        def mock_run(cmd, *args, **kwargs):
            if cmd and cmd[0] in ("ffprobe", "ffmpeg"):
                # Return mock output for ffprobe/ffmpeg
                from unittest.mock import MagicMock
                mock_result = MagicMock()
                mock_result.returncode = 0
                cmd_str = " ".join(cmd)
                # Check if it's a duration query
                if "format=duration" in cmd_str:
                    mock_result.stdout = "30.0\n"
                elif "width" in cmd_str or "height" in cmd_str or "r_frame_rate" in cmd_str:
                    if "print_format json" in cmd_str or "-of json" in cmd_str:
                        mock_result.stdout = '{"streams":[{"width":1920,"height":1080,"r_frame_rate":"30/1"}]}'
                    else:
                        mock_result.stdout = "1920\n1080\n30/1\n"
                elif "print_format json" in cmd_str or "-of json" in cmd_str:
                    mock_result.stdout = '{"format":{"duration":"30.0"},"streams":[{"width":1920,"height":1080,"r_frame_rate":"30/1"}]}'
                elif cmd[0] == "ffmpeg":
                    # Mock ffmpeg encoding - create output file
                    # Find output file path (last argument that ends with .mp4)
                    for arg in reversed(cmd):
                        if arg.endswith(".mp4"):
                            Path(arg).touch()
                            break
                    mock_result.stdout = ""
                else:
                    mock_result.stdout = ""
                mock_result.stderr = ""
                return mock_result
            return original_run(cmd, *args, **kwargs)
        patchers.append(patch.object(subprocess, "run", side_effect=mock_run))
        
        # Start all patchers
        for p in patchers:
            p.start()
        
        return patchers
    
    def cleanup(self):
        """Clean up test environment."""
        # Restore environment variables
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        
        # Remove temporary directory
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)


class PipelineTestContext:
    """Context manager for running pipeline tests with full isolation."""
    
    def __init__(self):
        self.env = TestEnvironment()
        self.patchers = []
        self.results = {}
        
    def __enter__(self):
        self.env.setup()
        self.patchers = self.env.apply_mocks()
        return self.env
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        for p in self.patchers:
            p.stop()
        self.env.cleanup()
        return False


def create_test_environment() -> TestEnvironment:
    """Factory function to create and setup test environment."""
    return TestEnvironment().setup()


# Convenience functions for test media access
def get_test_video_path(env: TestEnvironment, name: str) -> Optional[Path]:
    """Get path to test video by name."""
    return env.test_media.get(name)


def get_test_sidecar_path(env: TestEnvironment, name: str, ext: str = "json") -> Path:
    """Get path to sidecar file."""
    return env.content_dirs["sidecars"] / f"{name}.{ext}"


if __name__ == "__main__":
    # Quick verification
    print("Setting up test environment...")
    env = create_test_environment()
    print(f"Temp dir: {env.temp_dir}")
    print(f"DB path: {env.db_path}")
    print(f"Test videos: {list(env.test_media.keys())}")
    print(f"Content dirs: {list(env.content_dirs.keys())}")
    print("Test environment ready!")
    env.cleanup()
    print("Cleaned up.")