"""
Sync-out / anti-duplicate tests.

Verifies the deleted.log -> remote-deletion logic that stops a posted raw from
being re-downloaded/re-uploaded on the next sync_in. rclone is mocked.
"""
from pathlib import Path

import lib
from sync_out import SyncOut


def test_deleted_log_entries_deleted_remotely_and_archived(monkeypatch):
    # Seed a deleted.log the way video_processor writes it.
    dlog = lib.deleted_log()
    dlog.parent.mkdir(parents=True, exist_ok=True)
    dlog.write_text("Biocho/foo.mp4\nTeh_v1/bar.MOV\n", encoding="utf-8")

    deleted_calls = []
    fake_db = object()

    def fake_rclone(self, args, timeout=600):
        deleted_calls.append(args)
        return True, "ok"

    monkeypatch.setattr(SyncOut, "_rclone", fake_rclone)
    monkeypatch.setattr("sync_out.Database", lambda *a, **k: fake_db)

    s = SyncOut({"google_drive": {"rclone_remote": "gdrive:", "remote_path": "TikTokContent"}})
    result = s._delete_remote_processed()

    assert result == 2
    # Two deletefile calls, targeting the remote path.
    delete_calls = [a for a in deleted_calls if a[0] == "deletefile"]
    assert len(delete_calls) == 2
    remote_paths = {a[1] for a in delete_calls}
    assert "gdrive:TikTokContent/Biocho/foo.mp4" in remote_paths
    assert "gdrive:TikTokContent/Teh_v1/bar.MOV" in remote_paths

    # deleted.log is now empty (cleared after successful delete).
    assert dlog.read_text(encoding="utf-8").strip() == ""
    # Entries were archived to deleted_history.log.
    hist = dlog.with_name("deleted_history.log")
    hist_txt = hist.read_text(encoding="utf-8")
    assert "Biocho/foo.mp4" in hist_txt
    assert "Teh_v1/bar.MOV" in hist_txt


def test_failed_delete_keeps_entry_for_retry(monkeypatch):
    dlog = lib.deleted_log()
    dlog.parent.mkdir(parents=True, exist_ok=True)
    dlog.write_text("Biocho/foo.mp4\n", encoding="utf-8")

    def fake_rclone(self, args, timeout=600):
        return False, "remote gone or error"

    monkeypatch.setattr(SyncOut, "_rclone", fake_rclone)
    monkeypatch.setattr("sync_out.Database", lambda *a, **k: object())

    s = SyncOut({"google_drive": {"rclone_remote": "gdrive:", "remote_path": ""}})
    result = s._delete_remote_processed()

    assert result == 0  # nothing deleted
    # Entry kept so next sync_out retries it.
    assert dlog.read_text(encoding="utf-8").strip() == "Biocho/foo.mp4"


def test_empty_deleted_log_does_nothing(monkeypatch):
    dlog = lib.deleted_log()
    dlog.parent.mkdir(parents=True, exist_ok=True)
    dlog.write_text("", encoding="utf-8")

    called = []
    monkeypatch.setattr(SyncOut, "_rclone",
                        lambda self, args, timeout=600: called.append(args) or (True, "ok"))
    monkeypatch.setattr("sync_out.Database", lambda *a, **k: object())

    s = SyncOut({"google_drive": {}})
    assert s._delete_remote_processed() == 0
    assert called == []


def test_sync_runs_all_steps(monkeypatch):
    # Seed one raw so _copy_processed would normally fire; mock rclone so no
    # real rclone is invoked.
    lib.processed_dir().mkdir(parents=True, exist_ok=True)
    (lib.processed_dir() / "Biocho").mkdir(parents=True, exist_ok=True)
    (lib.processed_dir() / "Biocho" / "foo.mp4").write_bytes(b"x" * 100)
    dlog = lib.deleted_log()
    dlog.parent.mkdir(parents=True, exist_ok=True)
    dlog.write_text("Biocho/foo.mp4\n", encoding="utf-8")

    monkeypatch.setattr(SyncOut, "_rclone", lambda self, args, timeout=600: (True, "ok"))
    monkeypatch.setattr("sync_out.Database", lambda *a, **k: object())

    s = SyncOut({"google_drive": {"rclone_remote": "gdrive:", "remote_path": "TC"}})
    result = s.sync()
    assert result["deleted_remote"] == 1
