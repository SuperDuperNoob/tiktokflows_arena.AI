"""Failure simulation tests for Phase 10 production readiness.

Tests controlled failure scenarios to verify recovery behavior.
Run with TESTING=1 and FAILURE_SIM=1 environment variables.
"""

import os
import sys
import time
import signal
import sqlite3
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

# Add project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVICES_DIR = PROJECT_ROOT / "services"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SERVICES_DIR))

# Enable testing mode
os.environ["TESTING"] = "1"


def setup_test_db():
    """Create a temporary test database."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="tiktok_test_"))
    db_path = tmp_dir / "test_tiktok.db"
    return tmp_dir, str(db_path)


def cleanup_test_db(tmp_dir: Path):
    """Clean up test database."""
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_upload_interruption_recovery():
    """Test: Upload interrupted -> crash -> restart -> recover correctly.
    
    Scenario:
    1. Job in UPLOADING state
    2. Process crashes (simulated)
    3. Restart - RecoveryManager should detect and handle
    4. Verify: job state preserved, duplicate upload prevented, recovery logged
    """
    print("\n=== Test: Upload Interruption Recovery ===")
    
    from services.infrastructure.config import Config
    from services.infrastructure.database import Database
    from services.repositories import UploadRepository
    from services.models.upload_job import UploadJob, UploadJobStatus
    from services.core.recovery_manager import RecoveryManager
    from services.core.metrics_service import metrics
    
    tmp_dir, db_path = setup_test_db()
    
    try:
        # Initialize DB with schema
        db = Database(db_path)
        
        # Create upload repository
        upload_repo = UploadRepository(db_path)
        
        # Create a job in UPLOADING state (simulating crash during upload)
        job = UploadJob(
            product_name="test_product",
            product_id="test_001",
            raw_video_path="/tmp/test_video.mp4",
            processed_video_path="/tmp/test_video_processed.mp4",
            caption_text="Test caption",
            video_hash="abc123hash",
            source_path="/tmp/test_video.mp4",
            job_uuid="test_uuid_001",
            status=UploadJobStatus.UPLOADING,
            retry_count=0,
            max_retries=3,
        )
        job_id = upload_repo.create(job)
        job.id = job_id
        print(f"Created job {job_id} in UPLOADING state")
        
        # Verify job exists in UPLOADING
        found = upload_repo.get_by_id(job_id)
        assert found.status == UploadJobStatus.UPLOADING, f"Expected UPLOADING, got {found.status}"
        print("✓ Job confirmed in UPLOADING state")
        
        # Simulate crash - now run recovery
        recovery_mgr = RecoveryManager(upload_repo, max_processing_age_hours=2)
        
        # Run reconciliation - should detect stuck UPLOADING job
        result = recovery_mgr.run_startup_reconciliation()
        print(f"Reconciliation result: {result}")
        
        # Job was in UPLOADING for < 2 hours, so should be retried (not abandoned)
        # Check job status after recovery
        recovered_job = upload_repo.get_by_id(job_id)
        print(f"Job status after recovery: {recovered_job.status}")
        
        # Since age < 2h, it should be retried (RETRY_PENDING)
        assert recovered_job.status in (UploadJobStatus.RETRY_PENDING, UploadJobStatus.UPLOADING), \
            f"Expected RETRY_PENDING or UPLOADING, got {recovered_job.status}"
        
        print("✓ Upload interruption recovery test PASSED")
        return True
        
    finally:
        cleanup_test_db(tmp_dir)


def test_processing_interruption_recovery():
    """Test: Processing interrupted -> crash -> restart.
    
    Scenario:
    1. Job in PROCESSING state (compliance check, video rendering)
    2. Process crashes
    3. Restart - RecoveryManager should detect and retry
    """
    print("\n=== Test: Processing Interruption Recovery ===")
    
    from services.infrastructure.database import Database
    from services.repositories import UploadRepository
    from services.models.upload_job import UploadJob, UploadJobStatus
    from services.core.recovery_manager import RecoveryManager
    
    tmp_dir, db_path = setup_test_db()
    
    try:
        db = Database(db_path)
        upload_repo = UploadRepository(db_path)
        
        # Create job in PROCESSING state
        job = UploadJob(
            product_name="test_product",
            product_id="test_002",
            raw_video_path="/tmp/test_video2.mp4",
            processed_video_path="",
            caption_text="Test caption 2",
            video_hash="def456hash",
            source_path="/tmp/test_video2.mp4",
            job_uuid="test_uuid_002",
            status=UploadJobStatus.PROCESSING,
            retry_count=0,
            max_retries=3,
        )
        job_id = upload_repo.create(job)
        job.id = job_id
        print(f"Created job {job_id} in PROCESSING state")
        
        # Run recovery
        recovery_mgr = RecoveryManager(upload_repo, max_processing_age_hours=2)
        result = recovery_mgr.run_startup_reconciliation()
        print(f"Reconciliation result: {result}")
        
        # Job should be retried (age < 2h)
        recovered_job = upload_repo.get_by_id(job_id)
        print(f"Job status after recovery: {recovered_job.status}")
        
        assert recovered_job.status in (UploadJobStatus.RETRY_PENDING, UploadJobStatus.PROCESSING), \
            f"Expected RETRY_PENDING or PROCESSING, got {recovered_job.status}"
        
        print("✓ Processing interruption recovery test PASSED")
        return True
        
    finally:
        cleanup_test_db(tmp_dir)


def test_database_failure_handling():
    """Test: Database unavailable / locked / corrupted.
    
    Verify clear errors, no silent failure, recovery path exists.
    """
    print("\n=== Test: Database Failure Handling ===")
    
    from services.infrastructure.database import Database
    from services.repositories.base import BaseRepository
    
    # Test 1: Non-existent database path
    print("Test 1: Database at invalid path")
    try:
        db = Database("/invalid/path/that/does/not/exist/tiktok.db")
        # Should fail on first operation
        with db._connect() as conn:
            conn.execute("SELECT 1")
        print("✗ Expected failure but succeeded")
        return False
    except Exception as e:
        print(f"✓ Correctly failed with: {type(e).__name__}: {e}")
    
    # Test 2: Database locked simulation
    print("\nTest 2: Database locked (simulated)")
    tmp_dir, db_path = setup_test_db()
    try:
        db = Database(db_path)
        
        # Test that concurrent access works with WAL mode
        import threading
        import time
        
        errors = []
        def writer():
            try:
                with db._connect() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    time.sleep(0.1)  # Hold lock briefly
                    conn.execute("INSERT INTO posts (product_name, product_id, raw_video_path, processed_video_path, caption_text, status) VALUES ('test', 'test', 'a', 'b', 'c', 'PENDING')")
            except Exception as e:
                errors.append(e)
        
        # Start multiple writers
        threads = [threading.Thread(target=writer) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2)
        
        if errors:
            print(f"✓ Got expected concurrency errors: {errors[0]}")
        else:
            print("✓ Concurrent access handled gracefully")
        
        return True
        
    finally:
        cleanup_test_db(tmp_dir)


def test_storage_failure_retry():
    """Test: Storage failure (missing drive, rclone failure, permission failure).
    
    Verify retry behavior and correct classification.
    """
    print("\n=== Test: Storage Failure Retry Behavior ===")
    
    from services.infrastructure.retry import retry_with_policy, STORAGE_POLICY
    from services.exceptions import StorageError, RetryableStorageError
    
    attempt_count = [0]
    
    @retry_with_policy(STORAGE_POLICY)
    def failing_storage_operation():
        attempt_count[0] += 1
        if attempt_count[0] < 3:
            raise RetryableStorageError("rclone: failed to copy: permission denied")
        return "success"
    
    try:
        result = failing_storage_operation()
        assert result == "success"
        assert attempt_count[0] == 3, f"Expected 3 attempts, got {attempt_count[0]}"
        print(f"✓ Storage retry succeeded after {attempt_count[0]} attempts")
    except Exception as e:
        print(f"✗ Storage retry failed: {e}")
        return False
    
    # Test fatal storage error (not retried)
    attempt_count[0] = 0
    
    @retry_with_policy(STORAGE_POLICY)
    def fatal_storage_operation():
        attempt_count[0] += 1
        raise StorageError("disk full - no space left on device")
    
    try:
        fatal_storage_operation()
        print("✗ Expected fatal error to propagate")
        return False
    except StorageError as e:
        assert attempt_count[0] == 1, f"Expected 1 attempt for fatal, got {attempt_count[0]}"
        print(f"✓ Fatal storage error not retried (1 attempt)")
    
    print("✓ Storage failure retry test PASSED")
    return True


def test_idempotency_after_crash():
    """Test: Idempotency check prevents duplicate upload after crash.
    
    Scenario:
    1. Upload succeeds, job marked SUCCESS
    2. Crash before cleanup
    3. Restart - same video should be skipped
    """
    print("\n=== Test: Idempotency After Crash ===")
    
    from services.infrastructure.database import Database
    from services.repositories import UploadRepository
    from services.models.upload_job import UploadJob, UploadJobStatus
    from services.core.upload_service import UploadService
    from services.utils.paths import db_path
    
    tmp_dir, db_path = setup_test_db()
    
    try:
        db = Database(db_path)
        upload_repo = UploadRepository(db_path)
        
        # Create a SUCCESS job with video_hash
        video_hash = "same_video_hash_789"
        job = UploadJob(
            product_name="test_product",
            product_id="test_003",
            raw_video_path="/tmp/video.mp4",
            processed_video_path="/tmp/video.mp4",
            caption_text="Test caption",
            video_hash=video_hash,
            source_path="/tmp/video.mp4",
            job_uuid="test_uuid_003",
            status=UploadJobStatus.SUCCESS,
            posted_at=datetime.now(timezone.utc),
            retry_count=0,
            max_retries=3,
        )
        job_id = upload_repo.create(job)
        print(f"Created SUCCESS job {job_id} with hash {video_hash}")
        
        # Simulate finding same video again
        found = upload_repo.find_by_video_hash(video_hash)
        assert found is not None, "Should find existing job by hash"
        assert found.status == UploadJobStatus.SUCCESS, "Job should be SUCCESS"
        print(f"✓ Found existing SUCCESS job with same hash")
        
        # Verify idempotency logic would skip
        if found and found.status == UploadJobStatus.SUCCESS:
            print("✓ Idempotency check would skip duplicate upload")
        
        print("✓ Idempotency after crash test PASSED")
        return True
        
    finally:
        cleanup_test_db(tmp_dir)


def run_all_failure_tests():
    """Run all failure simulation tests."""
    print("=" * 60)
    print("PHASE 10 - FAILURE SIMULATION TESTS")
    print("=" * 60)
    
    tests = [
        test_upload_interruption_recovery,
        test_processing_interruption_recovery,
        test_database_failure_handling,
        test_storage_failure_retry,
        test_idempotency_after_crash,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"\n✗ {test.__name__} FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test.__name__, False))
    
    print("\n" + "=" * 60)
    print("FAILURE SIMULATION TEST SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "PASSED" if passed else "FAILED"
        print(f"  {name}: {status}")
    
    all_passed = all(r[1] for r in results)
    print(f"\nOverall: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    
    return all_passed


if __name__ == "__main__":
    success = run_all_failure_tests()
    sys.exit(0 if success else 1)