"""
Video processor tests: frame-count guard, quality floor, sidecar generation.
FFmpeg is not required for these - they exercise the pure-Python guards and
the sidecar I/O, using a synthetic burn log.
"""
import json
from pathlib import Path

import lib
from sidecar_manager import SidecarManager
from video_processor import generate_malay_caption


def test_min_output_frames_default():
    assert lib.MIN_OUTPUT_FRAMES == 10


def test_min_mb_per_sec_default():
    assert lib.MIN_MB_PER_SEC == 0.30


def test_quality_check_flags_still_image(tmp_path):
    burn = tmp_path / "burn_log.jsonl"
    # A burn with 2 frames is a still image (< 10).
    burn.write_text(json.dumps({
        "frames": 2, "duration_s": 0.1, "mb_per_sec": 0.5,
        "video_kbps": 100, "low_quality": False, "encode": {"crf": "23",
        "maxrate": "5M"}, "output_path": "/x/a.mp4",
    }) + "\n", encoding="utf-8")
    q = lib.quality_check(10, burn_path=burn)
    assert q["is_still"] is True
    assert q["still_count"] == 1


def test_quality_check_flags_low_bitrate(tmp_path):
    burn = tmp_path / "burn_log.jsonl"
    burn.write_text(json.dumps({
        "frames": 300, "duration_s": 10.0, "mb_per_sec": 0.10,
        "video_kbps": 80, "low_quality": True, "encode": {"crf": "30",
        "maxrate": "2M"}, "output_path": "/x/a.mp4",
    }) + "\n", encoding="utf-8")
    q = lib.quality_check(10, burn_path=burn)
    assert q["degraded"] is True
    assert q["latest_mb_per_sec"] < lib.MIN_MB_PER_SEC


def test_quality_check_clean(tmp_path):
    burn = tmp_path / "burn_log.jsonl"
    burn.write_text(json.dumps({
        "frames": 450, "duration_s": 15.0, "mb_per_sec": 1.2,
        "video_kbps": 900, "low_quality": False, "encode": {"crf": "23",
        "maxrate": "5M"}, "output_path": "/x/a.mp4",
    }) + "\n", encoding="utf-8")
    q = lib.quality_check(10, burn_path=burn)
    assert q["degraded"] is False
    assert q["is_still"] is False


def test_sidecar_write_read_cleanup(tmp_path):
    manager = SidecarManager(tmp_path)
    mp4 = tmp_path / "Biocho_123_45.mp4"
    mp4.write_bytes(b"fake-video-bytes")
    meta = {"product_id": "7398211122334455", "product_folder": "Biocho",
            "title": "Biocho 🔥", "caption": "beg kuning bawah",
            "hashtags": ["#biocho", "#murah"], "frames": 450}
    json_path, pid_path = manager.write(mp4, meta)

    assert json_path.exists()
    assert pid_path.exists()

    # JSON read returns the full dict.
    loaded = manager.read(mp4)
    assert loaded["product_id"] == "7398211122334455"
    assert loaded["product_folder"] == "Biocho"

    # PID read returns the legacy product_id|title|caption shape.
    pid_data = manager.read_pid(pid_path)
    assert pid_data["product_id"] == "7398211122334455"
    assert pid_data["title"] == "Biocho 🔥"

    # find() returns the triple.
    triples = manager.find()
    assert len(triples) == 1
    assert triples[0][0] == mp4

    # Cleanup removes both sidecars.
    manager.cleanup(mp4)
    assert not json_path.exists()
    assert not pid_path.exists()


def test_missing_sidecar_returns_none(tmp_path):
    manager = SidecarManager(tmp_path)
    mp4 = tmp_path / "bare.mp4"
    mp4.write_bytes(b"x")
    assert manager.read(mp4) is None


def test_generate_caption_is_compliant():
    from caption_policy import scan_caption
    for _ in range(30):
        cap = generate_malay_caption({"captions": ["beli sini", "cuba la"]},
                                     ["murah gila hari ni stok last"])
        assert scan_caption(cap)["needs_rewrite"] is False
        assert cap.strip()
