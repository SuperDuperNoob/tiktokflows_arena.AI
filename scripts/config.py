"""
Centralized Configuration Management

Single source of truth for configuration loading, validation, and access.
Replaces scattered config loading across modules.
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Optional

import yaml


class ConfigError(Exception):
    """Configuration error."""
    pass


class Config:
    """Centralized configuration manager with validation and reload support."""
    
    _instance: Optional["Config"] = None
    _lock = threading.Lock()
    
    # Required config keys that must be present
    REQUIRED_KEYS = {
        "telegram": ["bot_token", "allowed_user_id"],
        "proxy": ["endpoint"],
        "ai": ["base_url", "api_key"],
        "tiktok": ["session_username", "uploader_dir"],
    }
    
    # Default values for optional keys
    DEFAULTS = {
        "tiktok": {
            "session_username": "kumpul.shop",
            "uploader_dir": "/opt/TiktokAutoUploader",
            "cookie_max_age_days": 14,
        },
        "posting": {
            "interval_minutes": 120,
            "jitter_minutes": 30,
            "quiet_hours_start": 2,
            "quiet_hours_end": 6,
            "daily_post_target": 7,
        },
        "content": {
            "raw_dir": "content/raw",
            "processed_dir": "content/processed",
            "posted_dir": "content/posted",
            "failed_dir": "content/failed",
            "sounds_dir": "sounds",
            "captions_pool": "content/captions/pool.json",
            "min_stock_warning": 5,
            "preset_text": "content/raw/preset_text.txt",
            "product_id_file": "content/raw/product_id.txt",
        },
        "proxy": {
            "endpoint": "",
            "strict_mode": True,
            "geo_check": True,
            "expected_country": "MY",
            "verify_endpoint": "https://ipinfo.io/json",
            "datacenter_keywords": [
                "amazon", "digitalocean", "google cloud", "microsoft",
                "ovh", "linode", "vultr"
            ],
        },
        "ai": {
            "api_key": "",
            "base_url": "https://api.iamhc.cn/v1",
            "model": "auto",
            "growth_locale": "ms-MY",
            "enable_ai": False,
            "caption_per_video": False,
            "max_calls_per_day": 1,
            "timeout_seconds": 45,
            "retries": 2,
        },
        "compliance": {
            "strict_mode": True,
            "use_ai": True,
            "banned_phrases": [],
        },
        "encoding": {
            "crf": 23,
            "maxrate": "5M",
            "bufsize": "8M",
            "abr": "128k",
            "preset": "veryfast",
            "threads": 1,
            "min_mb_per_sec": 0.30,
            "min_output_frames": 10,
            "overlay_accent_rate": 0.15,
        },
        "rendering": {
            "force_style": None,
        },
        "analytics": {
            "rival_handle": "reski.reski700",
        },
        "google_drive": {
            "rclone_remote": "",
            "remote_path": "",
            "products_file": "content/products.json",
        },
        "apify": {
            "token": "",
            "actor_id": "clockworks/tiktok-scraper",
            "competitors": ["reski.reski700"],
            "results_per_page": 20,
            "max_competitors": 5,
            "scrape_schedule_hour": 3,
        },
        "telegram": {
            "bot_token": "",
            "allowed_user_id": 0,
        },
        "logging": {
            "db_path": "logs/tiktok.db",
        },
        "timezone": {
            "tz": "Asia/Kuala_Lumpur",
        },
    }
    
    def __init__(self, config_path: Optional[Path] = None):
        """Load configuration from YAML file."""
        self.config_path = config_path or self._find_config_path()
        self._data: dict = {}
        self._project_root: Path = self.config_path.parent.parent
        self._load()
    
    @classmethod
    def _find_config_path(cls) -> Path:
        """Find config.yaml in standard locations."""
        # Check environment variable first
        env_path = os.environ.get("TIKTOK_MACHINE_CONFIG")
        if env_path:
            return Path(env_path)
        
        # Check standard locations
        candidates = [
            Path.cwd() / "config" / "config.yaml",
            Path("/opt/tiktok-machine") / "config" / "config.yaml",
            Path.home() / "tiktokflow" / "tiktok-machine" / "config" / "config.yaml",
        ]
        
        for path in candidates:
            if path.exists():
                return path
        
        # Default to project root
        return Path.cwd() / "config" / "config.yaml"
    
    @property
    def project_root(self) -> Path:
        return self._project_root
    
    def _load(self) -> None:
        """Load and validate configuration."""
        if not self.config_path.exists():
            raise ConfigError(f"Config file not found: {self.config_path}")
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in config: {e}")
        
        if not isinstance(raw, dict):
            raise ConfigError("Config root must be a dictionary")
        
        # Merge with defaults
        self._data = self._merge_defaults(raw)
        
        # Apply environment variable overrides
        self._apply_env_overrides()
        
        # Validate required keys
        self._validate()
        
        # Resolve relative paths
        self._resolve_paths()
    
    def _merge_defaults(self, raw: dict) -> dict:
        """Deep merge raw config with defaults."""
        result = {}
        for section, defaults in self.DEFAULTS.items():
            section_data = raw.get(section, {})
            if isinstance(section_data, dict):
                result[section] = {**defaults, **section_data}
            else:
                result[section] = defaults.copy()
        
        # Preserve any extra sections not in defaults
        for key, value in raw.items():
            if key not in result:
                result[key] = value
        
        return result
    
    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides."""
        # Proxy endpoint
        if proxy_env := os.environ.get("TIKTOK_PROXY"):
            self._data.setdefault("proxy", {})["endpoint"] = proxy_env
        
        # AI API key
        if ai_key := os.environ.get("AI_API_KEY"):
            self._data.setdefault("ai", {})["api_key"] = ai_key
        
        # Timezone
        if tz := os.environ.get("TIKTOKFLOW_TZ"):
            self._data.setdefault("timezone", {})["tz"] = tz
        
        # Session user
        if user := os.environ.get("TIKTOK_SESSION_USER"):
            self._data.setdefault("tiktok", {})["session_username"] = user
        
        # Rival handle
        if rival := os.environ.get("TIKTOK_RIVAL_HANDLE"):
            self._data.setdefault("analytics", {})["rival_handle"] = rival
        
        # Home directory
        if home := os.environ.get("TIKTOKFLOW_HOME") or os.environ.get("TIKTOK_MACHINE_HOME"):
            self._project_root = Path(home).expanduser()
    
    def _validate(self) -> None:
        """Validate required configuration keys."""
        if os.environ.get("TESTING") == "1":
            return
        missing = []
        for section, keys in self.REQUIRED_KEYS.items():
            section_data = self._data.get(section, {})
            for key in keys:
                value = section_data.get(key)
                if not value or value in ("", 0, "your-api-key-here", "your-apify-token-here",
                                           "http://USER:PASS@HOST:PORT", "YOUR_BOT_TOKEN_HERE"):
                    missing.append(f"{section}.{key}")
        
        if missing:
            raise ConfigError(f"Missing required config keys: {', '.join(missing)}")
    
    def _resolve_paths(self) -> None:
        """Resolve relative paths to absolute."""
        path_sections = {
            "content": ["raw_dir", "processed_dir", "posted_dir", "failed_dir", 
                       "sounds_dir", "captions_pool", "preset_text", "product_id_file"],
            "logging": ["db_path"],
            "google_drive": ["products_file"],
            "tiktok": ["uploader_dir"],
        }
        
        for section, keys in path_sections.items():
            section_data = self._data.get(section, {})
            for key in keys:
                value = section_data.get(key)
                if value and isinstance(value, str) and not os.path.isabs(value):
                    section_data[key] = str(self._project_root / value)
    
    def reload(self) -> None:
        """Reload configuration from file."""
        with self._lock:
            self._load()
    
    def get(self, *path: str, default: Any = None) -> Any:
        """Get config value by path (e.g., get('proxy', 'endpoint'))."""
        node = self._data
        for key in path:
            if not isinstance(node, dict):
                return default
            node = node.get(key)
            if node is None:
                return default
        return node
    
    def get_section(self, section: str) -> dict:
        """Get entire config section."""
        return self._data.get(section, {}).copy()
    
    def set(self, section: str, key: str, value: Any) -> None:
        """Set a config value and save to file."""
        if section not in self._data:
            self._data[section] = {}
        self._data[section][key] = value
        self._save()
    
    def _save(self) -> None:
        """Save configuration to file atomically."""
        import tempfile
        import shutil
        
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, 
            dir=str(self.config_path.parent)
        ) as tmp:
            yaml.dump(self._data, tmp, default_flow_style=False, sort_keys=False)
            tmp_path = tmp.name
        
        shutil.move(tmp_path, self.config_path)
    
    @classmethod
    def get_instance(cls, config_path: Optional[Path] = None) -> "Config":
        """Get singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config_path)
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        with cls._lock:
            cls._instance = None


# Backward compatibility functions for lib.py
_CFG_INSTANCE: Optional[Config] = None


def get_config() -> Config:
    """Get the global config instance."""
    global _CFG_INSTANCE
    if _CFG_INSTANCE is None:
        _CFG_INSTANCE = Config.get_instance()
    return _CFG_INSTANCE


def reload_config() -> Config:
    """Force reload of configuration."""
    global _CFG_INSTANCE
    if _CFG_INSTANCE:
        _CFG_INSTANCE.reload()
    else:
        _CFG_INSTANCE = Config.get_instance()
    return _CFG_INSTANCE


def cfg(*path: str, default: Any = None) -> Any:
    """Get config value (backward compatible with lib.cfg)."""
    return get_config().get(*path, default=default)