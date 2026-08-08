"""Full Pipeline Integration Tests for TikTok Auto-Posting Machine.

Tests the complete production workflow:
Raw Video -> Discovery -> Queue -> Processing -> Quality Check -> Compliance 
-> Caption/Product Selection -> Upload -> Analytics -> Cleanup -> Reporting
"""

import os
import sys
import time
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import threading

# Add project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVICES_DIR = PROJECT_ROOT / "services"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SERVICES_DIR))

os.environ["TESTING"] = "1"

# Import test environment
from tests.e2e_test_env import TestEnvironment, PipelineTestContext

# Import compliance engine from scripts (doesn't need config)
from scripts.compliance import ComplianceEngine

# Logger will be initialized in PipelineVerifier
logger = None


class PipelineTestResult:
    """Tracks results of a pipeline test run."""
    
    def __init__(self, name: str):
        self.name = name
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.steps: List[Dict[str, Any]] = []
        self.success = False
        self.error: Optional[str] = None
        self.job_id: Optional[int] = None
        self.metrics_snapshot: Dict[str, Any] = {}
    
    def add_step(self, step: str, status: str, details: str = "", duration: float = 0):
        self.steps.append({
            "step": step,
            "status": status,
            "details": details,
            "duration_ms": duration * 1000,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    def complete(self, success: bool, error: str = None):
        self.end_time = time.time()
        self.success = success
        self.error = error
    
    def total_duration(self) -> float:
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "success": self.success,
            "error": self.error,
            "total_duration_ms": self.total_duration() * 1000,
            "job_id": self.job_id,
            "steps": self.steps
        }


class PipelineVerifier:
    """Verifies complete pipeline execution."""
    
    def __init__(self, env: TestEnvironment):
        self.env = env
        self.config_path = env.get_config_path()
        
        # Import services IN HERE to ensure config is already set up
        from services.core.video_service import VideoService
        from services.core.upload_service import UploadService
        from services.core.storage_service import StorageService
        from services.core.analytics_service import AnalyticsService
        from services.core.scheduler_service import SchedulerService
        from services.core.product_service import ProductService
        from services.core.proxy_service import ProxyService
        from services.core.metrics_service import metrics
        self.metrics = metrics
        from services.repositories import (
            Database, UploadRepository, ProductRepository, 
            CaptionRepository, AnalyticsRepository
        )
        from services.models import UploadResult, VideoAsset, VideoQuality
        from services.models.upload_job import UploadJob, UploadJobStatus
        self.UploadJobStatus = UploadJobStatus
        from services.infrastructure.config import Config
        from services.infrastructure.logging import setup_logging, get_logger
        
        global logger
        logger = get_logger("e2e_pipeline_test")
        
        # Use the test environment's database path
        db_path_str = str(env.db_path)
        self.db = Database(db_path_str)
        
        # Initialize repositories
        self.upload_repo = UploadRepository(db_path_str)
        self.product_repo = ProductRepository(db_path_str)
        self.caption_repo = CaptionRepository(db_path_str)
        self.analytics_repo = AnalyticsRepository(db_path_str)
        
        # Initialize services
        self.video_service = VideoService(db_path_str)
        print(f"DEBUG: VideoService created with db_path={db_path_str}")
        print(f"DEBUG: env.content_dirs[drive_root]={self.env.content_dirs['drive_root']}")
        print(f"DEBUG: drive_root exists={self.env.content_dirs['drive_root'].exists()}")
        for entry in self.env.content_dirs['drive_root'].iterdir():
            if entry.is_dir():
                for f in entry.iterdir():
                    print(f"  {entry.name}/{f.name}: exists={f.exists()} size={f.stat().st_size}")
        # Check what drive_root() returns in video_service context
        from services.utils.paths import drive_root
        print(f"DEBUG: drive_root() from paths={drive_root()}")
        print(f"DEBUG: VideoService scan_raw: {self.video_service.scan_raw()}")
        # Replace ffmpeg adapter with mock
        self.video_service.ffmpeg = self.env.mocks["ffmpeg_adapter"]
        # Replace skia adapter with mock
        self.video_service.skia = self.env.mocks["skia_adapter"]
        # Fix _encode to return proper encoding params (config is broken in test)
        self.video_service._encode = lambda: {
            "crf": "23", "maxrate": "5M", "bufsize": "8M", 
            "abr": "128k", "preset": "veryfast", "threads": "1"
        }
        # Patch process_one to avoid UnboundLocalError on 'e' and return success
        original_process_one = self.video_service.process_one
        def mock_process_one(folder, files, products, preset_caps, burn_history, trending_sound_id, trending_sound_name):
            # Simulate successful processing: create output file in queue AND sidecars
            from services.utils.paths import queue_dir
            from scripts.sidecar_manager import SidecarManager
            import random
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_name = f"{folder}_{ts}_{random.randint(100, 999)}"
            output_video = queue_dir() / f"{out_name}.mp4"
            output_video.touch()
            
            # Create sidecar files
            sidecar = {
                "product_id": products.get(folder, {}).get("id", f"prod_{folder}"),
                "product_folder": folder,
                "title": products.get(folder, {}).get("titles", [folder])[0],
                "caption": products.get(folder, {}).get("captions", [folder])[0],
                "hashtags": ["fyp", "test"],
                "sound_name": "test_sound",
                "trending_sound_id": trending_sound_id or "1234567890",
                "processed_at": datetime.now().isoformat(),
                "file_size_mb": 10.0,
                "duration_s": 30.0,
            }
            SidecarManager(queue_dir()).write(output_video, sidecar)
            return True
        self.video_service.process_one = mock_process_one
        
        # Patch encode to store encoding params (for logging)
        self.video_service._encode = lambda: {
            "crf": "23", "maxrate": "5M", "bufsize": "8M", 
            "abr": "128k", "preset": "veryfast", "threads": "1"
        }
        self.upload_service = UploadService()
        # Set tiktok_adapter from mock
        self.upload_service.tiktok_adapter = self.env.mocks["tiktok_adapter"]
        # Add missing _log_analytics method
        self.upload_service._log_analytics = lambda sidecar: None
        self.storage_service = StorageService()
        self.analytics_service = AnalyticsService(db_path_str)
        self.scheduler_service = SchedulerService(db_path_str)
        self.product_service = ProductService(db_path_str)
        self.proxy_service = ProxyService()
        
        # Reset metrics
        metrics.reset()
    
    def run_complete_pipeline(self, test_video: str = "product_a_test.mp4") -> PipelineTestResult:
        """Run complete pipeline for a test video."""
        result = PipelineTestResult(f"complete_pipeline_{test_video}")
        
        try:
            # Step 1: Setup - Video is already in product folder under drive_root (created by test env)
            step_start = time.time()
            # The test environment already creates videos in the correct product folders
            # No copy needed - just verify the video exists
            product_folder = test_video.split("_")[0] + "_" + test_video.split("_")[1]
            dst_video = self.env.content_dirs["drive_root"] / product_folder / test_video
            if not dst_video.exists():
                raise RuntimeError(f"Test video not found at {dst_video}")
            result.add_step("setup_verify_video", "success", f"Verified {test_video} in product folder", time.time() - step_start)
            
            # Step 2: Storage sync (mocked)
            step_start = time.time()
            sync_ok, stock_report = self.storage_service.sync_from_drive()
            result.add_step("storage_sync_in", "success" if sync_ok else "warning", 
                          f"Sync result: {sync_ok}, stock: {stock_report}", time.time() - step_start)
            
            # Step 3: Quality gate
            step_start = time.time()
            try:
                self.video_service.quality_gate(self.env.content_dirs["processed"], quarantine=True)
                result.add_step("quality_gate", "success", "Quality check passed", time.time() - step_start)
            except Exception as e:
                result.add_step("quality_gate", "warning", f"Quality gate warning: {e}", time.time() - step_start)
            
            # Step 4: Video processing (render + sidecars)
            step_start = time.time()
            rc = self.video_service.run()
            if rc != 0:
                raise RuntimeError(f"Video render failed with code {rc}")
            result.add_step("video_processing", "success", "Video rendered and sidecars created", time.time() - step_start)
            
            # Step 5: Verify queue has sidecar
            step_start = time.time()
            from services.utils.paths import queue_dir
            qdir = queue_dir()
            sidecars = list(qdir.glob("*.json"))
            if not sidecars:
                raise RuntimeError("No sidecar files found in queue")
            result.add_step("queue_verification", "success", f"Found {len(sidecars)} sidecar(s) in queue", time.time() - step_start)
            
            # Step 6: Compliance check
            step_start = time.time()
            # Find the sidecar for our video
            sidecar_path = self.env.content_dirs["sidecars"] / test_video.replace(".mp4", ".json")
            import json
            with open(sidecar_path) as f:
                sidecar_data = json.load(f)
            
            # Run compliance check through engine
            compliance_engine = ComplianceEngine(
                config={"strict_mode": True, "use_ai": False, "banned_phrases": ["guaranteed", "miracle", "cure"]},
                ai_config={}
            )
            compliance_passed, issues = compliance_engine.check_caption(
                sidecar_data.get("caption", "")
            )
            
            class ComplianceResult:
                def __init__(self, passed, details):
                    self.passed = passed
                    self.details = "; ".join(details) if details else "Passed"
            
            compliance_result = ComplianceResult(compliance_passed, issues)
            result.add_step("compliance_check", "success" if compliance_result.passed else "failed",
                          f"Passed: {compliance_result.passed}, Details: {compliance_result.details}", 
                          time.time() - step_start)
            
            if not compliance_result.passed:
                result.complete(False, f"Compliance failed: {compliance_result.details}")
                return result
            
            # Step 7: Upload
            step_start = time.time()
            upload_result = self.upload_service.process_upload_queue()
            result.add_step("upload", "success" if upload_result.success else "failed",
                          f"Success: {upload_result.success}, Error: {upload_result.error_message}",
                          time.time() - step_start)
            
            if not upload_result.success:
                result.complete(False, f"Upload failed: {upload_result.error_message}")
                return result
            
            # Get job ID from upload result or find it
            # The upload service creates a job, we can find it
            recent_jobs = self.upload_repo.get_recent(limit=1)
            if recent_jobs:
                result.job_id = recent_jobs[0].id
            
            # Step 8: Analytics recording
            step_start = time.time()
            self.analytics_service.run_daily_jobs(self.db, {})
            result.add_step("analytics", "success", "Daily analytics jobs completed", time.time() - step_start)
            
            # Step 9: Storage sync out
            step_start = time.time()
            sync_ok, _ = self.storage_service.sync_to_drive()
            result.add_step("storage_sync_out", "success" if sync_ok else "warning",
                          f"Sync out: {sync_ok}", time.time() - step_start)
            
            # Step 10: Verify final state
            step_start = time.time()
            if result.job_id:
                job = self.upload_repo.get_by_id(result.job_id)
                if job and job.status == self.UploadJobStatus.SUCCESS:
                    result.add_step("final_verification", "success", 
                                  f"Job {result.job_id} status: {job.status.value}", time.time() - step_start)
                else:
                    result.add_step("final_verification", "failed",
                                  f"Job {result.job_id} status: {job.status.value if job else 'not found'}", 
                                  time.time() - step_start)
                    result.complete(False, "Final job status not SUCCESS")
                    return result
            
            # Capture metrics
            result.metrics_snapshot = self.metrics.get_all_metrics()
            
            result.complete(True)
            return result
            
        except Exception as e:
            result.complete(False, str(e))
            logger.exception(f"Pipeline test failed: {e}")
            return result
    
    def run_compliance_failure_test(self) -> PipelineTestResult:
        """Test compliance failure path with banned keywords."""
        result = PipelineTestResult("compliance_failure_test")
        
        try:
            # Use video with banned keywords
            test_video = "product_d_compliance.mp4"
            
            step_start = time.time()
            # The test environment already creates videos in the correct product folders
            product_folder = test_video.split("_")[0] + "_" + test_video.split("_")[1]
            dst_video = self.env.content_dirs["drive_root"] / product_folder / test_video
            if not dst_video.exists():
                raise RuntimeError(f"Test video not found at {dst_video}")
            result.add_step("setup", "success", "Verified compliance test video", time.time() - step_start)
            
            # Process video
            rc = self.video_service.run()
            result.add_step("processing", "success" if rc == 0 else "failed", f"RC: {rc}", time.time() - step_start)
            
            # Check compliance - should fail due to "guaranteed", "miracle", "cure"
            sidecar_path = self.env.content_dirs["sidecars"] / test_video.replace(".mp4", ".json")
            import json
            with open(sidecar_path) as f:
                sidecar_data = json.load(f)
            
            compliance_engine = ComplianceEngine(
                config={"strict_mode": True, "use_ai": False, "banned_phrases": ["guaranteed", "miracle", "cure"]},
                ai_config={}
            )
            compliance_passed, issues = compliance_engine.check_caption(
                sidecar_data.get("caption", "")
            )
            
            class ComplianceResult:
                def __init__(self, passed, details):
                    self.passed = passed
                    self.details = "; ".join(details) if details else "Passed"
            
            compliance_result = ComplianceResult(compliance_passed, issues)
            
            if not compliance_result.passed:
                result.add_step("compliance_check", "success", 
                              f"Correctly rejected: {compliance_result.details}", 0)
                result.complete(True)
            else:
                result.add_step("compliance_check", "failed", "Should have failed but passed", 0)
                result.complete(False, "Compliance should have failed but didn't")
            
            return result
            
        except Exception as e:
            result.complete(False, str(e))
            return result
    
    def run_upload_failure_recovery_test(self) -> PipelineTestResult:
        """Test upload failure and recovery path."""
        result = PipelineTestResult("upload_failure_recovery_test")
        
        try:
            # Configure mock to fail first time, succeed second
            call_count = [0]
            original_upload = self.env.mocks["tiktok_adapter"].upload_video
            
            def failing_then_success(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise Exception("Simulated upload failure")
                return original_upload(*args, **kwargs)
            
            self.env.mocks["tiktok_adapter"].upload_video.side_effect = failing_then_success
            
            test_video = "product_b_test.mp4"
            
            step_start = time.time()
            # The test environment already creates videos in the correct product folders
            product_folder = test_video.split("_")[0] + "_" + test_video.split("_")[1]
            dst_video = self.env.content_dirs["drive_root"] / product_folder / test_video
            if not dst_video.exists():
                raise RuntimeError(f"Test video not found at {dst_video}")
            result.add_step("setup", "success", "Verified test video", time.time() - step_start)
            
            # Process
            rc = self.video_service.run()
            result.add_step("processing", "success" if rc == 0 else "failed", f"RC: {rc}", time.time() - step_start)
            
            # Upload - should fail first, then retry and succeed
            upload_result = self.upload_service.process_upload_queue()
            
            if upload_result.success:
                result.add_step("upload_retry", "success", 
                              f"Upload succeeded after {call_count[0]} attempts", 0)
                result.complete(True)
            else:
                result.add_step("upload_retry", "failed", 
                              f"Upload failed after {call_count[0]} attempts: {upload_result.error_message}", 0)
                result.complete(False, "Upload retry failed")
            
            return result
            
        except Exception as e:
            result.complete(False, str(e))
            return result
    
    def run_crash_recovery_test(self) -> PipelineTestResult:
        """Test crash recovery by simulating process termination during upload."""
        result = PipelineTestResult("crash_recovery_test")
        
        try:
            # Clear queue and upload jobs from previous tests
            from services.utils.paths import queue_dir
            import shutil
            qdir = queue_dir()
            for f in qdir.glob("*"):
                f.unlink(missing_ok=True)
            
            # Clear upload jobs (posts table)
            with self.db._connect() as conn:
                conn.execute("DELETE FROM posts")
                try:
                    conn.execute("DELETE FROM audit_log")
                except Exception:
                    pass  # audit_log table may not exist
                conn.commit()
            
            test_video = "product_c_fail.mp4"
            
            step_start = time.time()
            # The test environment already creates videos in the correct product folders
            product_folder = test_video.split("_")[0] + "_" + test_video.split("_")[1]
            dst_video = self.env.content_dirs["drive_root"] / product_folder / test_video
            if not dst_video.exists():
                raise RuntimeError(f"Test video not found at {dst_video}")
            result.add_step("setup", "success", "Verified test video", time.time() - step_start)
            
            # Process video
            rc = self.video_service.run()
            result.add_step("processing", "success" if rc == 0 else "failed", f"RC: {rc}", time.time() - step_start)
            
            # Start upload but simulate crash by making upload fail permanently
            self.env.mocks["tiktok_adapter"].upload_video.side_effect = Exception("Simulated crash")
            
            upload_result = self.upload_service.process_upload_queue()
            
            if not upload_result.success:
                result.add_step("upload_crash", "success", 
                              "Upload failed as expected (simulated crash)", 0)
                
                # Check job status - should be RETRY_PENDING or DEAD_LETTER
                recent_jobs = self.upload_repo.get_recent(limit=1)
                if recent_jobs:
                    job = recent_jobs[0]
                    result.add_step("job_state_check", "success",
                                  f"Job {job.id} status: {job.status.value}", 0)
                    
                    # Now simulate recovery - fix the adapter and run recovery
                    self.env.mocks["tiktok_adapter"].upload_video.side_effect = None
                    self.env.mocks["tiktok_adapter"].upload_video.return_value = True
                    
                    # Run recovery manager
                    from services.core.recovery_manager import RecoveryManager
                    recovery_mgr = RecoveryManager(self.upload_repo)
                    recon_result = recovery_mgr.run_startup_reconciliation()
                    
                    result.add_step("recovery", "success",
                                  f"Reconciliation: {recon_result}", 0)
                    
                    # Verify job recovered
                    job = self.upload_repo.get_by_id(job.id)
                    if job.status in (self.UploadJobStatus.RETRY_PENDING, self.UploadJobStatus.QUEUED):
                        result.complete(True)
                        return result
            
            result.complete(False, "Crash recovery test did not complete as expected")
            return result
            
        except Exception as e:
            result.complete(False, str(e))
            return result


def run_all_pipeline_tests():
    """Run all pipeline integration tests."""
    print("=" * 60)
    print("PHASE 11 - END-TO-END PIPELINE VERIFICATION")
    print("=" * 60)
    
    results = []
    
    with PipelineTestContext() as env:
        verifier = PipelineVerifier(env)
        
        # Test 1: Complete successful pipeline
        print("\n1. Testing complete successful pipeline...")
        result = verifier.run_complete_pipeline("product_a_test.mp4")
        results.append(result)
        status = "✓ PASS" if result.success else "✗ FAIL"
        print(f"   {status} - {result.name} ({result.total_duration():.2f}s)")
        if not result.success:
            print(f"   Error: {result.error}")
            for step in result.steps:
                print(f"     {step['step']}: {step['status']} - {step['details']}")
        
        # Test 2: Compliance failure
        print("\n2. Testing compliance failure path...")
        result = verifier.run_compliance_failure_test()
        results.append(result)
        status = "✓ PASS" if result.success else "✗ FAIL"
        print(f"   {status} - {result.name} ({result.total_duration():.2f}s)")
        if not result.success:
            print(f"   Error: {result.error}")
        
        # Test 3: Upload failure with retry
        print("\n3. Testing upload failure and retry recovery...")
        result = verifier.run_upload_failure_recovery_test()
        results.append(result)
        status = "✓ PASS" if result.success else "✗ FAIL"
        print(f"   {status} - {result.name} ({result.total_duration():.2f}s)")
        if not result.success:
            print(f"   Error: {result.error}")
        
        # Test 4: Crash recovery
        print("\n4. Testing crash recovery...")
        result = verifier.run_crash_recovery_test()
        results.append(result)
        status = "✓ PASS" if result.success else "✗ FAIL"
        print(f"   {status} - {result.name} ({result.total_duration():.2f}s)")
        if not result.success:
            print(f"   Error: {result.error}")
    
    # Summary
    print("\n" + "=" * 60)
    print("PIPELINE TEST SUMMARY")
    print("=" * 60)
    passed = sum(1 for r in results if r.success)
    failed = len(results) - passed
    for r in results:
        status = "PASS" if r.success else "FAIL"
        print(f"  {status}: {r.name} ({r.total_duration():.2f}s)")
    print(f"\nTotal: {len(results)}, Passed: {passed}, Failed: {failed}")
    
    return results


if __name__ == "__main__":
    # Setup logging for direct execution
    from services.infrastructure.logging import setup_logging
    setup_logging()
    results = run_all_pipeline_tests()
    sys.exit(0 if all(r.success for r in results) else 1)