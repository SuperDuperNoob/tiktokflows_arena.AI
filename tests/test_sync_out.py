"""
Sync-out / anti-duplicate tests (DB-ledger design).

"Already posted" is recorded in SQLite (raw_stock.posted_at). sync_out reads
the DB and deletes the Drive copy as COSMETIC cleanup. A failed delete is safe
— the raw is still excluded from selection, so it can never be re-uploaded.
rclone is mocked.
"""
import lib
from sync_drive import DriveSyncer
from sync_out import SyncOut


def _consume(product, filename, file_hash="abc123"):
    lib.mark_raw_consumed(product, filename, file_hash=file_hash)


def test_delete_remote_deletes_consumed_and_marks_cleaned(monkeypatch):
    _consume("Biocho", "foo.mp4")
    _consume("Teh_v1", "bar.MOV")

    delete_calls = []

    def fake_rclone(self, args, timeout=600):
        if args and args[0] == "deletefile":
            delete_calls.append(args[1])
        return True, "ok"

    monkeypatch.setattr(SyncOut, "_rclone", fake_rclone)
    s = SyncOut({"google_drive": {"rclone_remote": "gdrive:", "remote_path": "TikTokContent"}})

    assert s._delete_remote() == 2
    assert set(delete_calls) == {
        "gdrive:TikTokContent/Biocho/foo.mp4",
        "gdrive:TikTokContent/Teh_v1/bar.MOV",
    }

    # Both marked cleaned -> no longer pending.
    assert lib.consumed_pending_cleanup() == []


def test_failed_delete_keeps_pending_and_does_not_duplicate(monkeypatch):
    _consume("Biocho", "foo.mp4")

    def fake_rclone(self, args, timeout=600):
        return False, "remote gone or error"

    monkeypatch.setattr(SyncOut, "_rclone", fake_rclone)
    s = SyncOut({"google_drive": {"rclone_remote": "gdrive:", "remote_path": "TikTokContent"}})

    assert s._delete_remote() == 0
    # Still pending -> retried next run. But it is consumed, so the selector
    # (get_unused_raw_videos) will NOT return it -> no duplicate upload.
    assert len(lib.consumed_pending_cleanup()) == 1
    from db import Database
    db = Database(str(lib.db_path()))
    unused = db.get_unused_raw_videos("Biocho")
    assert all(u["filename"] != "foo.mp4" for u in unused)


def test_nothing_pending_does_nothing(monkeypatch):
    called = []
    monkeypatch.setattr(SyncOut, "_rclone",
                        lambda self, args, timeout=600: called.append(args) or (True, "ok"))
    s = SyncOut({"google_drive": {"rclone_remote": "gdrive:", "remote_path": "TikTokContent"}})
    assert s._delete_remote() == 0
    assert called == []


def test_consumed_raw_excluded_from_stock_counts():
    from db import Database
    db = Database(str(lib.db_path()))
    db.sync_raw_stock("Biocho", ["a.mp4", "b.mp4"])
    lib.mark_raw_consumed("Biocho", "a.mp4", "h")
    counts = db.get_raw_stock_counts()
    # Only the not-yet-consumed file counts.
    assert counts.get("Biocho") == 1


def test_sync_in_and_sync_out_resolve_same_remote():
    """Anti-duplicate loop only works if both syncs point at the same Drive
    folder, regardless of trailing colon."""
    for given in ("gdrive:", "gdrive"):
        sd = DriveSyncer({"rclone_remote": given, "remote_path": "TikTokContent"}, None)
        so = SyncOut({"google_drive": {"rclone_remote": given, "remote_path": "TikTokContent"}})
        assert sd._remote_root() == "gdrive:TikTokContent"
        assert so._remote_root() == "gdrive:TikTokContent"
        assert sd._remote_root() == so._remote_root()


def test_sync_runs_all_steps(monkeypatch):
    _consume("Biocho", "foo.mp4")
    lib.processed_dir().mkdir(parents=True, exist_ok=True)
    (lib.processed_dir() / "Biocho").mkdir(parents=True, exist_ok=True)
    (lib.processed_dir() / "Biocho" / "foo.mp4").write_bytes(b"x" * 100)

    monkeypatch.setattr(SyncOut, "_rclone", lambda self, args, timeout=600: (True, "ok"))
    s = SyncOut({"google_drive": {"rclone_remote": "gdrive:", "remote_path": "TC"}})
    result = s.sync()
    assert result["deleted_remote"] == 1
