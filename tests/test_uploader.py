"""
Uploader tests: proxy shorthand parsing, geo-check logic, strict-mode behaviour.
External APIs are mocked - no real proxy traffic in the test suite.
"""
import os

from services.utils.proxy import (check_proxy_exit, is_proxy_transport_error, mask_proxy,
                 normalize_proxy_url)
from uploader import Uploader


# ---- proxy shorthand parsing ------------------------------------------------

def test_proxy_canonical_url_passthrough():
    assert normalize_proxy_url("http://u:p@h:8080") == "http://u:p@h:8080"


def test_proxy_user_pass_at_host_port():
    assert normalize_proxy_url("user:pass@host:8080") == "http://user:pass@host:8080"


def test_proxy_user_pass_host_port_shorthand():
    assert normalize_proxy_url("user:pass:host:8080") == "http://user:pass@host:8080"


def test_proxy_host_port_user_pass_alternate():
    assert normalize_proxy_url("host:8080:user:pass") == "http://user:pass@host:8080"


def test_proxy_host_port_only():
    assert normalize_proxy_url("host:8080") == "http://host:8080"


def test_proxy_socks_kept():
    assert normalize_proxy_url("socks5://u:p@h:1080") == "socks5://u:p@h:1080"


def test_proxy_empty_returns_empty():
    assert normalize_proxy_url("") == ""
    assert normalize_proxy_url("   ") == ""


def test_proxy_urlencodes_special_chars():
    # 4-part shorthand goes through quote() so '+' in a username is encoded.
    out = normalize_proxy_url("u+ser:pass:123.45.67.89:8080")
    assert "u%2Bser" in out


# ---- masked logging ---------------------------------------------------------

def test_mask_proxy_hides_password():
    masked = mask_proxy("user:password123:123.45.67.89:8080")
    assert "password123" not in masked
    assert masked.startswith("http://use***@123.45.67.89:8080")


def test_mask_proxy_none_for_empty():
    assert mask_proxy("") is None


# ---- geo-check logic --------------------------------------------------------

def _fake_ipapi(country="MY", hosting=False, mobile=False):
    class Resp:
        status_code = 200

        def json(self):
            return {"status": "success", "country": "Malaysia",
                    "countryCode": country, "city": "KL",
                    "isp": "Maxis", "org": "Maxis Mobile",
                    "mobile": mobile, "proxy": False, "hosting": hosting,
                    "query": "1.2.3.4"}

    return Resp()


def test_geo_check_ok_my_residential(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **k: _fake_ipapi("MY", hosting=False))
    ok, detail = check_proxy_exit("http://u:p@h:8080")
    assert ok is True
    assert "MY" in detail


def test_geo_check_bad_wrong_country(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **k: _fake_ipapi("US", hosting=False))
    ok, _ = check_proxy_exit("http://u:p@h:8080")
    assert ok is False


def test_geo_check_bad_datacenter(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **k: _fake_ipapi("MY", hosting=True))
    ok, detail = check_proxy_exit("http://u:p@h:8080")
    assert ok is False
    assert "DATACENTER" in detail


def test_geo_check_ipinfo_fallback(monkeypatch):
    # ip-api raises -> fallback to ipinfo.io
    real_calls = {"n": 0}

    def fake_get(url, **kw):
        if "ip-api" in url:
            raise RuntimeError("ip-api down")
        real_calls["n"] += 1
        class R:
            status_code = 200

            def json(self):
                return {"ip": "1.2.3.4", "country": "MY", "city": "KL",
                        "org": "Maxis"}
        return R()

    monkeypatch.setattr("requests.get", fake_get)
    ok, _ = check_proxy_exit("http://u:p@h:8080")
    assert ok is True
    assert real_calls["n"] == 1


# ---- strict mode ------------------------------------------------------------

def _uploader_with_proxy(strict: bool, monkeypatch):
    # Route proxy through env so Uploader picks it up regardless of temp config.
    os.environ["TIKTOK_PROXY"] = "user:pass:123.45.67.89:8080"
    os.environ["TIKTOK_PROXY_STRICT"] = "1" if strict else "0"
    # Bad proxy exit: wrong country.
    monkeypatch.setattr("requests.get",
                        lambda *a, **k: _fake_ipapi("US", hosting=False))
    u = Uploader(config={"proxy": {"strict_mode": strict}}, dry_run=False)
    return u


def test_strict_mode_aborts_on_bad_proxy(monkeypatch):
    u = _uploader_with_proxy(strict=True, monkeypatch=monkeypatch)
    assert u.strict_mode is True
    assert u.verify_proxy() is False  # aborts before upload


def test_non_strict_warns_but_continues(monkeypatch):
    u = _uploader_with_proxy(strict=False, monkeypatch=monkeypatch)
    assert u.strict_mode is False
    assert u.verify_proxy() is True  # warn but continue


def test_strict_dry_run_continues(monkeypatch):
    os.environ["TIKTOK_PROXY"] = "user:pass:123.45.67.89:8080"
    os.environ["TIKTOK_PROXY_STRICT"] = "1"
    monkeypatch.setattr("requests.get",
                        lambda *a, **k: _fake_ipapi("US", hosting=False))
    u = Uploader(config={"proxy": {"strict_mode": True}}, dry_run=True)
    assert u.verify_proxy() is True  # dry-run continues


def test_no_proxy_skips_geo_check(monkeypatch):
    os.environ.pop("TIKTOK_PROXY", None)
    monkeypatch.setattr("requests.get",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not call")))
    # Mock config to return empty proxy
    import services.infrastructure.config as config_module
    original_get = config_module.get_config
    def mock_get_config():
        cfg = original_get()
        # Override proxy endpoint to empty
        cfg._data["proxy"]["endpoint"] = ""
        return cfg
    monkeypatch.setattr(config_module, "get_config", mock_get_config)
    u = Uploader(config={}, dry_run=True)
    assert u.proxy_url is None
    assert u.verify_proxy() is True


# ---- transport-error classification ----------------------------------------

def test_proxy_transport_error_detection():
    import requests
    assert is_proxy_transport_error(requests.exceptions.ProxyError())
    assert is_proxy_transport_error(requests.exceptions.ConnectTimeout())
    assert is_proxy_transport_error(RuntimeError("cannot connect to proxy"))
    assert not is_proxy_transport_error(ValueError("API returned False"))
