"""
Competitor scraper tests: actor choice, Apify call wiring, and the analytics
schema mapping that reconcile/ai_growth depend on. Apify HTTP is mocked.
"""
import datetime

from services.infrastructure.database import Database
import lib
from competitor_scraper import CompetitorScraper, DEFAULT_ACTOR


def _sample_item(vid_id, handle="reski.reski700"):
    return {
        "id": vid_id,
        "text": "murah gila #begkuning #promo 🔥",
        "authorMeta": {"name": handle, "fans": 123456},
        "musicMeta": {"musicId": "7001", "musicName": "viral sound",
                      "musicAuthor": "author"},
        "playCount": 15000,
        "diggCount": 800,
        "shareCount": 120,
        "commentCount": 40,
        "hashtags": [{"name": "begkuning"}, {"name": "promo"}],
        "createTime": 1750000000,
        "webVideoUrl": f"https://www.tiktok.com/@{handle}/video/{vid_id}",
    }


def _fake_db():
    class _DB:
        def save_competitor_data(self, entries):
            self.saved = entries

        def log_event(self, *a, **k):
            pass
    return _DB()


def test_default_actor_is_clockworks_tiktok_scraper():
    assert DEFAULT_ACTOR == "clockworks/tiktok-scraper"


def test_scraper_defaults_own_and_rival_handles():
    s = CompetitorScraper({"token": "tok"}, _fake_db())
    assert lib.OWN_HANDLE in s.competitors
    assert lib.RIVAL_HANDLE in s.competitors


def test_analytics_store_writes_competitor_tables():
    s = CompetitorScraper({"token": "tok"}, _fake_db())
    videos = [_sample_item("1111"), _sample_item("2222", handle="kumpul.shop")]
    s._store("reski.reski700", videos)

    conn = lib.get_conn()
    daily = conn.execute("SELECT * FROM competitor_daily WHERE handle=?",
                         ("reski.reski700",)).fetchall()
    assert len(daily) == 1
    d = daily[0]
    assert d["top_views"] == 15000
    assert d["top_sound_name"] == "viral sound"
    assert d["top_hashtag"] == "begkuning"
    assert d["posts_today"] == 2

    rows = conn.execute("SELECT * FROM competitor_videos WHERE handle=?",
                        ("reski.reski700",)).fetchall()
    assert len(rows) == 2
    v = conn.execute("SELECT * FROM competitor_videos WHERE video_id='1111'").fetchone()
    assert v["views"] == 15000
    assert v["likes"] == 800
    assert v["shares"] == 120
    assert v["comments"] == 40
    assert v["sound_name"] == "viral sound"
    assert "begkuning" in v["hashtags_json"]
    assert v["posted_at"]  # parsed from createTime
    conn.close()


def test_scrape_all_writes_through_mocked_apify(monkeypatch):
    db = _fake_db()
    s = CompetitorScraper({"token": "tok", "competitors": ["reski.reski700"]}, db)

    monkeypatch.setattr(s, "_start_actor_run", lambda inp: "run123")
    monkeypatch.setattr(s, "_wait_for_run", lambda rid, timeout: "ds123")
    monkeypatch.setattr(s, "_fetch_dataset_items",
                        lambda ds: [_sample_item("3333")])

    summary = s.scrape_all()
    assert summary.get("reski.reski700", {}).get("posts_scraped") == 1
    assert db.saved and db.saved[0]["view_count"] == 15000

    conn = lib.get_conn()
    n = conn.execute("SELECT COUNT(*) c FROM competitor_videos "
                     "WHERE video_id='3333'").fetchone()["c"]
    conn.close()
    assert n == 1
