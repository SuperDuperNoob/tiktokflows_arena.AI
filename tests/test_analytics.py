"""
Web analytics endpoint tests: verifies the chart-data queries return the right
shape from the analytics schema (views over time, per product).
"""
import lib
import conftest


def _seed():
    conn = lib.get_conn()
    lib.ensure_schema(conn)
    # Two own videos, three daily snapshots with cumulative views.
    conn.execute(
        "INSERT INTO videos(video_id, product_folder, caption, posted_at) "
        "VALUES('v1','Biocho','x','2026-08-01T10:00:00+00:00')")
    conn.execute(
        "INSERT INTO videos(video_id, product_folder, caption, posted_at) "
        "VALUES('v2','Teh','y','2026-08-02T10:00:00+00:00')")
    snaps = [
        ("v1", "2026-08-01", 100),
        ("v2", "2026-08-01", 50),
        ("v1", "2026-08-02", 300),
        ("v2", "2026-08-02", 200),
        ("v1", "2026-08-03", 500),
        ("v2", "2026-08-03", 250),
    ]
    for vid, d, views in snaps:
        conn.execute(
            "INSERT INTO daily_metrics(video_id,snap_date,views,captured_at) "
            "VALUES(?,?,?,?)", (vid, d, views, "t"))
    conn.commit()
    conn.close()


def test_views_by_day_series():
    _seed()
    conn = lib.get_conn()
    since = "2026-07-27"
    rows = [dict(r) for r in conn.execute(
        """SELECT snap_date, SUM(views) AS views FROM daily_metrics
           WHERE snap_date >= ? GROUP BY snap_date ORDER BY snap_date""",
        (since,))]
    conn.close()
    dates = [r["snap_date"] for r in rows]
    assert dates == ["2026-08-01", "2026-08-02", "2026-08-03"]
    # Totals: day1=150, day2=500, day3=750
    assert [r["views"] for r in rows] == [150, 500, 750]


def test_net_new_views_delta():
    _seed()
    conn = lib.get_conn()
    since = "2026-07-27"
    rows = [dict(r) for r in conn.execute(
        """SELECT snap_date, SUM(views) AS views FROM daily_metrics
           WHERE snap_date >= ? GROUP BY snap_date ORDER BY snap_date""",
        (since,))]
    conn.close()
    deltas, prev = [], 0
    for row in rows:
        cur = int(row["views"] or 0)
        deltas.append(max(0, cur - prev))
        prev = cur
    assert deltas == [150, 350, 250]


def test_product_views_latest_snapshot():
    _seed()
    conn = lib.get_conn()
    since = "2026-07-27"
    rows = [dict(r) for r in conn.execute(
        """WITH latest AS (
               SELECT video_id, views,
                      ROW_NUMBER() OVER (PARTITION BY video_id
                                         ORDER BY snap_date DESC) AS rn
               FROM daily_metrics WHERE snap_date >= ?
           )
           SELECT COALESCE(NULLIF(v.product_folder,''),'(unassigned)') AS product,
                  CAST(SUM(l.views) AS INTEGER) AS views
           FROM latest l JOIN videos v ON v.video_id = l.video_id
           WHERE l.rn = 1
           GROUP BY product_folder ORDER BY views DESC""", (since,))]
    conn.close()
    by = {r["product"]: r["views"] for r in rows}
    assert by == {"Biocho": 500, "Teh": 250}


def test_posts_by_day():
    _seed()
    conn = lib.get_conn()
    since = "2026-07-27"
    rows = [dict(r) for r in conn.execute(
        """SELECT substr(posted_at,1,10) AS day, COUNT(*) AS n
           FROM videos WHERE posted_at >= ? GROUP BY day ORDER BY day""",
        (since,))]
    conn.close()
    assert {r["day"]: r["n"] for r in rows} == {"2026-08-01": 1, "2026-08-02": 1}
