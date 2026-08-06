"""Security audit utilities for configuration and secrets management."""

import os
import re
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from dataclasses import dataclass, field
import logging


@dataclass
class SecretFinding:
    """Represents a detected secret in configuration."""
    file_path: str
    key_path: str
    value: str
    severity: str  # "critical", "high", "medium", "low"
    secret_type: str  # "password", "token", "api_key", "cookie", "proxy", "other"
    line_number: Optional[int] = None


@dataclass
class AuditResult:
    """Result of a security audit."""
    findings: List[SecretFinding] = field(default_factory=list)
    files_scanned: int = 0
    secrets_found: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0


class SecretsAuditor:
    """Audits configuration files for exposed secrets."""
    
    # Patterns for detecting secrets
    SECRET_PATTERNS = {
        "api_key": [
            r"(?i)api[_-]?key\s*[:=]\s*[\"']?([a-zA-Z0-9_\-]{20,})[\"']?",
            r"(?i)apikey\s*[:=]\s*[\"']?([a-zA-Z0-9_\-]{20,})[\"']?",
        ],
        "token": [
            r"(?i)token\s*[:=]\s*[\"']?([a-zA-Z0-9_\-\.]{20,})[\"']?",
            r"(?i)access[_-]?token\s*[:=]\s*[\"']?([a-zA-Z0-9_\-\.]{20,})[\"']?",
            r"(?i)bearer\s+([a-zA-Z0-9_\-\.]{20,})",
        ],
        "password": [
            r"(?i)password\s*[:=]\s*[\"']?([^\"'\s]{8,})[\"']?",
            r"(?i)passwd\s*[:=]\s*[\"']?([^\"'\s]{8,})[\"']?",
            r"(?i)secret\s*[:=]\s*[\"']?([^\"'\s]{8,})[\"']?",
        ],
        "cookie": [
            r"(?i)cookie\s*[:=]\s*[\"']?([^\"'\s]{20,})[\"']?",
            r"(?i)session[_-]?id\s*[:=]\s*[\"']?([^\"'\s]{20,})[\"']?",
        ],
        "proxy": [
            r"(?i)proxy\s*[:=]\s*[\"']?(https?://[^\"'\s]+)[\"']?",
            r"(?i)proxy[_-]?url\s*[:=]\s*[\"']?(https?://[^\"'\s]+)[\"']?",
        ],
        "database_url": [
            r"(?i)database[_-]?url\s*[:=]\s*[\"']?([^\"'\s]+)[\"']?",
            r"(?i)db[_-]?url\s*[:=]\s*[\"']?([^\"'\s]+)[\"']?",
        ],
    }
    
    # Keys that are known to contain secrets (for YAML/JSON traversal)
    SECRET_KEYS = {
        "api_key", "apikey", "token", "access_token", "refresh_token",
        "password", "passwd", "secret", "secret_key", "private_key",
        "cookie", "session_id", "session_cookie", "csrf_token",
        "proxy", "proxy_url", "proxy_endpoint", "proxy_password",
        "database_url", "db_url", "connection_string",
        "webhook_url", "webhook_secret",
        "aws_access_key_id", "aws_secret_access_key",
        "gcp_credentials", "azure_key",
    }
    
    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path.cwd()
    
    def audit_config_file(self, file_path: Path) -> List[SecretFinding]:
        """Audit a single configuration file for secrets."""
        findings = []
        
        try:
            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            
            # Scan line by line for patterns
            for line_num, line in enumerate(lines, 1):
                for secret_type, patterns in self.SECRET_PATTERNS.items():
                    for pattern in patterns:
                        matches = re.finditer(pattern, line)
                        for match in matches:
                            value = match.group(1) if match.groups() else match.group(0)
                            # Skip if value looks like a placeholder
                            if self._is_placeholder(value):
                                continue
                            findings.append(SecretFinding(
                                file_path=str(file_path.relative_to(self.project_root)),
                                key_path=f"line_{line_num}",
                                value=value,
                                severity=self._get_severity(secret_type),
                                secret_type=secret_type,
                                line_number=line_num,
                            ))
            
            # Also parse YAML/JSON for nested secrets
            if file_path.suffix in [".yaml", ".yml"]:
                findings.extend(self._audit_yaml_structure(file_path, content))
            elif file_path.suffix == ".json":
                findings.extend(self._audit_json_structure(file_path, content))
                
        except Exception as e:
            logging.warning(f"Failed to audit {file_path}: {e}")
        
        return findings
    
    def _audit_yaml_structure(self, file_path: Path, content: str) -> List[SecretFinding]:
        """Audit YAML structure for nested secrets."""
        findings = []
        try:
            data = yaml.safe_load(content)
            if data:
                findings.extend(self._traverse_dict(data, "", file_path))
        except Exception:
            pass
        return findings
    
    def _audit_json_structure(self, file_path: Path, content: str) -> List[SecretFinding]:
        """Audit JSON structure for nested secrets."""
        findings = []
        try:
            import json
            data = json.loads(content)
            findings.extend(self._traverse_dict(data, "", file_path))
        except Exception:
            pass
        return findings
    
    def _traverse_dict(self, data: Any, path: str, file_path: Path) -> List[SecretFinding]:
        """Recursively traverse dict/list for secret keys."""
        findings = []
        if isinstance(data, dict):
            for key, value in data.items():
                new_path = f"{path}.{key}" if path else key
                if isinstance(value, (dict, list)):
                    findings.extend(self._traverse_dict(value, new_path, file_path))
                elif isinstance(value, str) and key.lower() in self.SECRET_KEYS:
                    if not self._is_placeholder(value):
                        findings.append(SecretFinding(
                            file_path=str(file_path.relative_to(self.project_root)),
                            key_path=new_path,
                            value=value,
                            severity=self._get_severity_from_key(key),
                            secret_type=self._get_secret_type_from_key(key),
                        ))
        elif isinstance(data, list):
            for i, item in enumerate(data):
                findings.extend(self._traverse_dict(item, f"{path}[{i}]", file_path))
        return findings
    
    def _is_placeholder(self, value: str) -> bool:
        """Check if value is a placeholder/template."""
        placeholders = [
            "REDACTED", "***", "****", "******", "********",
            "your_key", "your_token", "your_password", "your_secret",
            "changeme", "change_me", "insert_here", "TODO",
            "env:", "${", "{{", "REDACTED",
        ]
        value_lower = value.lower()
        return any(p.lower() in value_lower for p in placeholders)
    
    def _get_severity(self, secret_type: str) -> str:
        """Get severity for secret type."""
        severity_map = {
            "api_key": "critical",
            "token": "critical",
            "password": "high",
            "cookie": "high",
            "proxy": "medium",
            "database_url": "high",
        }
        return severity_map.get(secret_type, "medium")
    
    def _get_severity_from_key(self, key: str) -> str:
        """Get severity from key name."""
        key_lower = key.lower()
        if any(k in key_lower for k in ["api_key", "token", "secret", "private_key"]):
            return "critical"
        if any(k in key_lower for k in ["password", "cookie", "database"]):
            return "high"
        if "proxy" in key_lower:
            return "medium"
        return "medium"
    
    def _get_secret_type_from_key(self, key: str) -> str:
        """Get secret type from key name."""
        key_lower = key.lower()
        if "api_key" in key_lower or "apikey" in key_lower:
            return "api_key"
        if "token" in key_lower:
            return "token"
        if "password" in key_lower or "passwd" in key_lower:
            return "password"
        if "cookie" in key_lower or "session" in key_lower:
            return "cookie"
        if "proxy" in key_lower:
            return "proxy"
        if "database" in key_lower or "db_" in key_lower:
            return "database_url"
        return "other"
    
    def audit_project(self, config_dirs: Optional[List[str]] = None) -> AuditResult:
        """Audit entire project for secrets."""
        result = AuditResult()
        
        # Default config directories
        if config_dirs is None:
            config_dirs = ["config", "scripts", "services"]
        
        for config_dir in config_dirs:
            dir_path = self.project_root / config_dir
            if not dir_path.exists():
                continue
            
            for file_path in dir_path.rglob("*"):
                if file_path.is_file() and file_path.suffix in [".yaml", ".yml", ".json", ".env", ".conf", ".ini", ".py"]:
                    # Skip test files and generated files
                    if any(skip in str(file_path) for skip in ["__pycache__", ".pytest_cache", "test_", "_test.py"]):
                        continue
                    
                    result.files_scanned += 1
                    findings = self.audit_config_file(file_path)
                    result.findings.extend(findings)
        
        # Count severities
        for f in result.findings:
            if f.severity == "critical":
                result.critical_count += 1
            elif f.severity == "high":
                result.high_count += 1
            elif f.severity == "medium":
                result.medium_count += 1
            elif f.severity == "low":
                result.low_count += 1
        
        result.secrets_found = len(result.findings)
        return result
    
    def generate_report(self, result: AuditResult) -> str:
        """Generate human-readable audit report."""
        lines = [
            "=" * 60,
            "SECRETS AUDIT REPORT",
            "=" * 60,
            f"Files scanned: {result.files_scanned}",
            f"Secrets found: {result.secrets_found}",
            f"  Critical: {result.critical_count}",
            f"  High:     {result.high_count}",
            f"  Medium:   {result.medium_count}",
            f"  Low:      {result.low_count}",
            "",
        ]
        
        if result.findings:
            lines.append("FINDINGS:")
            lines.append("-" * 60)
            for finding in sorted(result.findings, key=lambda f: (f.severity, f.file_path)):
                lines.append(f"  [{f.severity.upper()}] {f.file_path}:{f.key_path}")
                lines.append(f"    Type: {f.secret_type}")
                lines.append(f"    Value: {self._mask_value(f.value)}")
                lines.append("")
        else:
            lines.append("No secrets detected.")
        
        return "\n".join(lines)
    
    def _mask_value(self, value: str, show_chars: int = 4) -> str:
        """Mask a secret value for display."""
        if len(value) <= show_chars * 2:
            return "*" * len(value)
        return value[:show_chars] + "*" * (len(value) - show_chars * 2) + value[-show_chars:]


class SecretMasker:
    """Masks secrets in configuration data for safe logging/diagnostics."""
    
    MASK_PATTERNS = [
        (re.compile(r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\']?([^"\'\s]+)'), r'\1=****'),
        (re.compile(r'(?i)(token|access[_-]?token)\s*[:=]\s*["\']?([^"\'\s]+)'), r'\1=****'),
        (re.compile(r'(?i)(password|passwd|secret)\s*[:=]\s*["\']?([^"\'\s]+)'), r'\1=****'),
        (re.compile(r'(?i)(cookie|session[_-]?id)\s*[:=]\s*["\']?([^"\'\s]+)'), r'\1=****'),
        (re.compile(r'(?i)(proxy[_-]?(?:url|endpoint)?)\s*[:=]\s*["\']?(https?://[^"\'\s]+)'), r'\1=****'),
    ]
    
    @classmethod
    def mask_dict(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively mask secrets in a dictionary."""
        if not isinstance(data, dict):
            return data
        
        masked = {}
        for key, value in data.items():
            if isinstance(value, dict):
                masked[key] = cls.mask_dict(value)
            elif isinstance(value, list):
                masked[key] = [cls.mask_dict(v) if isinstance(v, dict) else cls._mask_string(v) for v in value]
            elif isinstance(value, str):
                masked[key] = cls._mask_string(value)
            else:
                masked[key] = value
        return masked
    
    @classmethod
    def _mask_string(cls, value: str) -> str:
        """Mask secrets in a string."""
        for pattern, replacement in cls.MASK_PATTERNS:
            value = pattern.sub(replacement, value)
        return value
    
    @classmethod
    def mask_yaml(cls, content: str) -> str:
        """Mask secrets in YAML content."""
        masked = content
        for pattern, replacement in cls.MASK_PATTERNS:
            masked = pattern.sub(replacement, masked)
        return masked


def audit_secrets(project_root: Optional[str] = None) -> AuditResult:
    """Convenience function to audit project secrets."""
    auditor = SecretsAuditor(Path(project_root) if project_root else None)
    return auditor.audit_project()


def mask_secrets(data: Any) -> Any:
    """Convenience function to mask secrets in data."""
    if isinstance(data, dict):
        return SecretMasker.mask_dict(data)
    elif isinstance(data, str):
        return SecretMasker.mask_yaml(data)
    return data