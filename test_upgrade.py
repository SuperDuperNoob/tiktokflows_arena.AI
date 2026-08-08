#!/usr/bin/env python3
"""Test upgrade path from old database to latest schema."""

import os
import sys
import sqlite3

# Set up paths like orchestrator.py does - MUST BE FIRST
# __file__ is /home/archery/fresh_install_test/tiktokflows_arena.AI/test_upgrade.py
# The test file is in the repo root, so PROJECT_ROOT is the directory containing the test file
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
SERVICES_DIR = os.path.join(PROJECT_ROOT, "services")
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SCRIPTS_DIR)

# Set environment - use absolute path for config - MUST BE BEFORE IMPORTS
os.environ["TIKTOK_MACHINE_CONFIG"] = os.path.join(PROJECT_ROOT, "config", "config.yaml")
os.environ["TESTING"] = "1"

# Verify config file exists
config_path = os.environ["TIKTOK_MACHINE_CONFIG"]
print(f"Config path: {config_path}")
print(f"Config exists: {os.path.exists(config_path)}")

# Now import after setting up paths and env
from services.infrastructure.database import Database


def create_old_database(db_path: str) -> str:
    """Create a database with an old schema (simulating v1)."""
    # Remove existing
    import os
    if os.path.exists(db_path):
        os.remove(db_path)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create minimal old schema (v1 - no schema_version table, no video_hash index)
    cursor.execute("""
        CREATE TABLE posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            product_id TEXT NOT NULL,
            raw_video_path TEXT NOT NULL,
            processed_video_path TEXT NOT NULL,
            caption_text TEXT NOT NULL,
            description_text TEXT,
            product_tag_text TEXT,
            sound_file TEXT,
            speed_factor REAL,
            brightness_shift REAL,
            posted_at DATETIME,
            status TEXT DEFAULT 'PENDING',
            tiktok_post_id TEXT,
            views INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            last_analytics_check DATETIME,
            proxy_ip_used TEXT,
            notes TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE raw_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            filename TEXT NOT NULL,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_used DATETIME,
            use_count INTEGER DEFAULT 0,
            file_hash TEXT,
            posted_at TEXT,
            drive_cleaned_at TEXT,
            UNIQUE(product_name, filename)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE caption_pool (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT,
            caption_text TEXT NOT NULL,
            description_text TEXT,
            product_tag_text TEXT,
            compliance_checked INTEGER DEFAULT 0,
            times_used INTEGER DEFAULT 0,
            last_used DATETIME,
            source TEXT DEFAULT 'manual',
            original_text TEXT,
            UNIQUE(product_name, caption_text)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE competitor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_handle TEXT NOT NULL,
            post_url TEXT,
            product_keywords TEXT,
            hashtags TEXT,
            sound_used TEXT,
            view_count INTEGER,
            caption_text TEXT,
            scraped_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE system_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            message TEXT,
            metadata TEXT,
            occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Add some test data
    cursor.execute("""
        INSERT INTO posts (product_name, product_id, raw_video_path, processed_video_path, caption_text, status)
        VALUES ('test_product', 'test_001', '/path/video.mp4', '/path/video_proc.mp4', 'Test caption', 'SUCCESS')
    """)
    
    cursor.execute("""
        INSERT INTO raw_stock (product_name, filename, posted_at)
        VALUES ('test_product', 'video.mp4', '2026-01-01 10:00:00')
    """)
    
    conn.commit()
    conn.close()
    
    print(f"Created old database at {db_path}")
    return db_path


def test_upgrade():
    """Test upgrading from old schema to latest."""
    db_path = "/tmp/test_upgrade.db"
    
    # Create old database
    create_old_database(db_path)
    
    # Verify old schema
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check posts table columns
    cursor.execute("PRAGMA table_info(posts)")
    old_cols = {row[1] for row in cursor.fetchall()}
    print(f"Old posts columns: {sorted(old_cols)}")
    
    # Check if schema_version table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
    has_version_table = cursor.fetchone() is not None
    print(f"Has schema_version table: {has_version_table}")
    
    # Check if video_hash index exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_posts_video_hash'")
    has_hash_index = cursor.fetchone() is not None
    print(f"Has video_hash index: {has_hash_index}")
    
    conn.close()
    
    # Now upgrade using Database class
    print("\n--- Running upgrade ---")
    db = Database(db_path)
    
    # Verify upgrade
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check schema_version table
    cursor.execute("SELECT * FROM schema_version")
    versions = cursor.fetchall()
    print(f"Schema versions after upgrade: {versions}")
    
    # Check posts table columns
    cursor.execute("PRAGMA table_info(posts)")
    new_cols = {row[1] for row in cursor.fetchall()}
    print(f"New posts columns: {sorted(new_cols)}")
    
    # Check video_hash index
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_posts_video_hash'")
    has_hash_index = cursor.fetchone() is not None
    print(f"Has video_hash index after upgrade: {has_hash_index}")
    
    # Check data preserved
    cursor.execute("SELECT COUNT(*) FROM posts")
    post_count = cursor.fetchone()[0]
    print(f"Posts count preserved: {post_count}")
    
    cursor.execute("SELECT COUNT(*) FROM raw_stock")
    stock_count = cursor.fetchone()[0]
    print(f"Raw stock count preserved: {stock_count}")
    
    conn.close()
    
    # Verify expected columns added
    expected_new_cols = {
        'video_hash', 'source_path', 'job_uuid', 'compliance_status', 
        'compliance_details', 'retry_count', 'max_retries', 'last_error',
        'created_at', 'updated_at', 'description_text', 'product_tag_text'
    }
    missing = expected_new_cols - new_cols
    if missing:
        print(f"WARNING: Missing columns: {missing}")
        return False
    else:
        print("SUCCESS: All expected columns added!")
    
    return True


if __name__ == "__main__":
    success = test_upgrade()
    sys.exit(0 if success else 1)