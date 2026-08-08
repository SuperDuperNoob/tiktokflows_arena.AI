#!/usr/bin/env python3
"""
Performance benchmark for TikTok Auto-Posting Machine.
Measures pipeline stages, resource usage, and database efficiency.
"""

import os
import sys
import time
import json
import psutil
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager
from typing import Dict, List, Any

# Add project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SERVICES_DIR = PROJECT_ROOT / "services"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SERVICES_DIR))

os.environ["TESTING"] = "1"

from services.infrastructure.config import Config
from services.infrastructure.database import Database
from services.repositories import (
    Database as RepoDatabase,
    UploadRepository,
    ProductRepository,
    StockRepository,
    CaptionRepository,
)
from services.core import (
    VideoService,
    UploadService,
    StorageService,
    AnalyticsService,
    SchedulerService,
    ProductService,
    ProxyService,
)
from services.infrastructure.logging import setup_logging, get_logger

logger = get_logger("benchmark")


@contextmanager
def measure_resources():
    """Context manager to measure CPU, memory, disk I/O."""
    process = psutil.Process()
    
    # Initial measurements
    cpu_start = process.cpu_times()
    mem_start = process.memory_info()
    io_start = process.io_counters() if hasattr(process, 'io_counters') else None
    
    wall_start = time.perf_counter()
    
    result = {}
    yield result
    
    wall_end = time.perf_counter()
    cpu_end = process.cpu_times()
    mem_end = process.memory_info()
    io_end = process.io_counters() if hasattr(process, 'io_counters') else None
    
    result["wall_time_ms"] = (wall_end - wall_start) * 1000
    result["cpu_user_ms"] = (cpu_end.user - cpu_start.user) * 1000
    result["cpu_system_ms"] = (cpu_end.system - cpu_start.system) * 1000
    result["memory_rss_mb"] = mem_end.rss / (1024 * 1024)
    result["memory_vms_mb"] = mem_end.vms / (1024 * 1024)
    result["memory_delta_mb"] = (mem_end.rss - mem_start.rss) / (1024 * 1024)
    
    if io_start and io_end:
        result["disk_read_mb"] = (io_end.read_bytes - io_start.read_bytes) / (1024 * 1024)
        result["disk_write_mb"] = (io_end.write_bytes - io_start.write_bytes) / (1024 * 1024)


class PerformanceBenchmark:
    """Run performance benchmarks on the pipeline."""
    
    def __init__(self):
        self.results = {}
        self.temp_dir = None
        self.db_path = None
        
    def setup(self):
        """Create isolated test environment."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="tiktok_benchmark_"))
        self.db_path = self.temp_dir / "benchmark.db"
        
        # Create config
        config_dir = self.temp_dir / "config"
        config_dir.mkdir()
        
        config_content = f"""
content:
  raw_dir: content/raw
  processed_dir: content/processed
  queue_dir: content/queue
  failed_dir: content/failed
  sidecar_dir: content/sidecars
  logs_dir: logs
  sounds_dir: content/sounds

encoding:
  crf: 23
  maxrate: "5M"
  bufsize: "8M"
  abr: "128k"
  preset: "veryfast"
  threads: 1

proxy:
  endpoint: ""
  strict_mode: false
  geo_check: false

posting:
  daily_post_target: 7
  jitter_min_seconds: 5
  jitter_max_seconds: 90

logging:
  db_path: {self.db_path}
  level: INFO
"""
        (config_dir / "config.yaml").write_text(config_content)
        
        # Create directory structure
        for d in ["content/raw", "content/processed", "content/queue", "content/failed", 
                  "content/sidecars", "logs", "content/sounds"]:
            (self.temp_dir / d).mkdir(parents=True, exist_ok=True)
            
        # Create product directories in raw
        for folder in ["product_a", "product_b", "product_c", "product_d"]:
            (self.temp_dir / "content/raw" / folder).mkdir(parents=True, exist_ok=True)
            
        # Create test config for services
        os.environ["TIKTOK_MACHINE_CONFIG"] = str(config_dir / "config.yaml")
        os.environ["TIKTOK_PROXY_GEO_CHECK"] = "false"
        os.environ["TIKTOK_PROXY_STRICT"] = "false"
        os.environ["TIKTOK_PROXY"] = ""
        
        # Initialize database with schema
        db = Database(str(self.db_path))
        
        # Add test data
        self._create_test_data()
        
        logger.info(f"Benchmark environment created at {self.temp_dir}")
        
    def _create_test_data(self):
        """Create synthetic test data for benchmarking."""
        import sqlite3
        import random
        
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        
        # Add test products
        products = [
            ("product_a", "prod_a_001", "Amazing Product A"),
            ("product_b", "prod_b_002", "Product B Unboxing"),
            ("product_c", "prod_c_003", "Failed Product"),
            ("product_d", "prod_d_004", "Compliance Test"),
        ]
        
        for folder, pid, title in products:
            conn.execute(
                "INSERT OR IGNORE INTO raw_stock (product_name, filename) VALUES (?, ?)",
                (folder, f"{folder}_video.mp4")
            )
            
            conn.execute(
                "INSERT OR IGNORE INTO caption_pool (product_name, caption_text, compliance_checked) VALUES (?, ?, 1)",
                (folder, f"Check out {title}!")
            )
        
        conn.commit()
        conn.close()
        
    def benchmark_database_ops(self, iterations: int = 100) -> Dict[str, Any]:
        """Benchmark database operations."""
        from services.infrastructure.database import Database
        from services.repositories import UploadRepository, ProductRepository, StockRepository
        
        db = Database(str(self.db_path))
        upload_repo = UploadRepository(str(self.db_path))
        product_repo = ProductRepository(str(self.db_path))
        stock_repo = StockRepository(str(self.db_path))
        
        results = {}
        
        # Benchmark: get_raw_stock_counts
        with measure_resources() as m:
            for _ in range(iterations):
                stock_repo.get_stock_counts()
        results["get_stock_counts"] = dict(m)
        
        # Benchmark: get_unused_raw_videos
        with measure_resources() as m:
            for _ in range(iterations):
                stock_repo.get_unused_videos("product_a")
        results["get_unused_videos"] = dict(m)
        
        # Benchmark: get_posts_today
        with measure_resources() as m:
            for _ in range(iterations):
                db.get_posts_today()
        results["get_posts_today"] = dict(m)
        
        # Benchmark: get_posted_count_today
        with measure_resources() as m:
            for _ in range(iterations):
                db.get_posted_count_today()
        results["get_posted_count_today"] = dict(m)
        
        # Benchmark: sync_raw_stock
        with measure_resources() as m:
            for i in range(iterations):
                db.sync_raw_stock("product_a", [f"test_video_{i}.mp4"])
        results["sync_raw_stock"] = dict(m)
        
        # Benchmark: UploadRepository find_by_video_hash
        with measure_resources() as m:
            for i in range(iterations):
                upload_repo.find_by_video_hash(f"hash_{i}")
        results["find_by_video_hash"] = dict(m)
        
        # Benchmark: UploadRepository get_recent
        with measure_resources() as m:
            for _ in range(iterations):
                upload_repo.get_recent(10)
        results["get_recent_uploads"] = dict(m)
        
        return results
        
    def benchmark_video_service(self, iterations: int = 10) -> Dict[str, Any]:
        """Benchmark video service operations."""
        from services.core.video_service import VideoService
        
        video_service = VideoService(str(self.db_path))
        results = {}
        
        # Benchmark: scan_raw
        with measure_resources() as m:
            for _ in range(iterations):
                video_service.scan_raw()
        results["scan_raw"] = dict(m)
        
        # Benchmark: load_products
        with measure_resources() as m:
            for _ in range(iterations):
                video_service.load_products()
        results["load_products"] = dict(m)
        
        # Benchmark: load_captions
        with measure_resources() as m:
            for _ in range(iterations):
                video_service.load_captions()
        results["load_captions"] = dict(m)
        
        # Benchmark: query_analytics_weights
        with measure_resources() as m:
            for _ in range(iterations):
                video_service.query_analytics_weights()
        results["query_analytics_weights"] = dict(m)
        
        # Benchmark: md5_file (create test file first)
        test_file = self.temp_dir / "content/raw/product_a/test_video.mp4"
        test_file.write_bytes(b"x" * 10_000_000)  # 10MB test file
        
        with measure_resources() as m:
            for _ in range(iterations):
                video_service.md5_file(test_file)
        results["md5_file_10mb"] = dict(m)
        
        test_file.unlink(missing_ok=True)
        
        return results
        
    def benchmark_upload_service(self, iterations: int = 10) -> Dict[str, Any]:
        """Benchmark upload service operations."""
        from services.core.upload_service import UploadService
        
        upload_service = UploadService()
        results = {}
        
        # Benchmark: verify_proxy (no proxy configured)
        with measure_resources() as m:
            for _ in range(iterations):
                upload_service.verify_proxy()
        results["verify_proxy_no_proxy"] = dict(m)
        
        # Benchmark: check_cookie_expiry
        with measure_resources() as m:
            for _ in range(iterations):
                upload_service.check_cookie_expiry()
        results["check_cookie_expiry"] = dict(m)
        
        # Benchmark: md5_file
        test_file = self.temp_dir / "test_upload.mp4"
        test_file.write_bytes(b"x" * 5_000_000)  # 5MB
        
        with measure_resources() as m:
            for _ in range(iterations):
                from services.core.upload_service import md5_file
                md5_file(test_file)
        results["md5_file_5mb"] = dict(m)
        
        test_file.unlink(missing_ok=True)
        
        return results
        
    def benchmark_analytics_service(self, iterations: int = 5) -> Dict[str, Any]:
        """Benchmark analytics service operations."""
        from services.core.analytics_service import AnalyticsService
        from services.infrastructure.database import Database
        
        db = Database(str(self.db_path))
        analytics = AnalyticsService(str(self.db_path))
        results = {}
        
        # Benchmark: get_performance_summary
        with measure_resources() as m:
            for _ in range(iterations):
                db.get_performance_summary(7)
        results["get_performance_summary"] = dict(m)
        
        # Benchmark: get_products_due_next
        with measure_resources() as m:
            for _ in range(iterations):
                db.get_products_due_next()
        results["get_products_due_next"] = dict(m)
        
        return results
        
    def benchmark_full_cycle(self, iterations: int = 3) -> Dict[str, Any]:
        """Benchmark a full pipeline cycle (without actual upload)."""
        from services.core import (
            VideoService, UploadService, StorageService,
            AnalyticsService, SchedulerService, ProductService, ProxyService
        )
        
        results = {}
        
        for i in range(iterations):
            cycle_results = {}
            
            # Create fresh services for each cycle
            video_service = VideoService(str(self.db_path))
            storage_service = StorageService()
            upload_service = UploadService()
            analytics_service = AnalyticsService(str(self.db_path))
            scheduler_service = SchedulerService(str(self.db_path))
            product_service = ProductService(str(self.db_path))
            proxy_service = ProxyService()
            
            # 1. Storage sync
            with measure_resources() as m:
                sync_ok, stock = storage_service.sync_from_drive()
            cycle_results["sync_from_drive"] = dict(m)
            
            # 2. Quality gate
            with measure_resources() as m:
                try:
                    video_service.quality_gate(self.temp_dir / "content/processed", quarantine=True)
                except Exception as e:
                    pass  # Expected in test
            cycle_results["quality_gate"] = dict(m)
            
            # 3. Video processing (dry run)
            with measure_resources() as m:
                rc = video_service.run(dry_run=True)
            cycle_results["video_processing_dry"] = dict(m)
            
            # 4. Upload queue check
            with measure_resources() as m:
                result = upload_service.process_upload_queue()
            cycle_results["process_upload_queue"] = dict(m)
            
            # 5. Analytics daily jobs
            with measure_resources() as m:
                try:
                    analytics_service.run_daily_jobs(
                        type('obj', (object,), {'execute': lambda *a, **k: None})(),
                        {}
                    )
                except Exception:
                    pass
            cycle_results["analytics_daily_jobs"] = dict(m)
            
            # Aggregate
            for k, v in cycle_results.items():
                if k not in results:
                    results[k] = []
                results[k].append(v)
                
        # Average the results
        avg_results = {}
        for k, v_list in results.items():
            if v_list:
                avg_results[k] = {
                    "wall_time_ms": sum(r.get("wall_time_ms", 0) for r in v_list) / len(v_list),
                    "cpu_user_ms": sum(r.get("cpu_user_ms", 0) for r in v_list) / len(v_list),
                    "memory_delta_mb": sum(r.get("memory_delta_mb", 0) for r in v_list) / len(v_list),
                }
                
        return avg_results
        
    def run_all_benchmarks(self) -> Dict[str, Any]:
        """Run all benchmarks and return consolidated results."""
        logger.info("Starting performance benchmarks...")
        
        all_results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": {
                "python_version": sys.version,
                "cpu_count": psutil.cpu_count(),
                "memory_total_gb": psutil.virtual_memory().total / (1024**3),
            },
            "benchmarks": {}
        }
        
        # Database operations
        logger.info("Running database benchmarks...")
        all_results["benchmarks"]["database"] = self.benchmark_database_ops(100)
        
        # Video service
        logger.info("Running video service benchmarks...")
        all_results["benchmarks"]["video_service"] = self.benchmark_video_service(10)
        
        # Upload service
        logger.info("Running upload service benchmarks...")
        all_results["benchmarks"]["upload_service"] = self.benchmark_upload_service(10)
        
        # Analytics service
        logger.info("Running analytics service benchmarks...")
        all_results["benchmarks"]["analytics_service"] = self.benchmark_analytics_service(5)
        
        # Full cycle
        logger.info("Running full cycle benchmarks...")
        all_results["benchmarks"]["full_cycle"] = self.benchmark_full_cycle(3)
        
        logger.info("All benchmarks completed")
        return all_results
        
    def cleanup(self):
        """Clean up test environment."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            logger.info(f"Cleaned up {self.temp_dir}")


def main():
    setup_logging()
    
    benchmark = PerformanceBenchmark()
    try:
        benchmark.setup()
        results = benchmark.run_all_benchmarks()
        
        # Save results
        output_file = PROJECT_ROOT / "benchmark_results.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
            
        logger.info(f"Benchmark results saved to {output_file}")
        
        # Print summary
        print("\n" + "="*60)
        print("PERFORMANCE BENCHMARK SUMMARY")
        print("="*60)
        
        for category, benchmarks in results["benchmarks"].items():
            print(f"\n{category.upper()}:")
            for name, metrics in benchmarks.items():
                if isinstance(metrics, dict) and "wall_time_ms" in metrics:
                    print(f"  {name}: {metrics['wall_time_ms']:.2f}ms wall, "
                          f"{metrics['cpu_user_ms']:.2f}ms CPU, "
                          f"{metrics.get('memory_delta_mb', 0):.2f}MB delta")
                elif isinstance(metrics, list):
                    avg_wall = sum(m.get("wall_time_ms", 0) for m in metrics) / len(metrics) if metrics else 0
                    print(f"  {name}: {avg_wall:.2f}ms avg wall time ({len(metrics)} runs)")
                    
        return 0
        
    except Exception as e:
        logger.exception("Benchmark failed: %s", e)
        return 1
    finally:
        benchmark.cleanup()


if __name__ == "__main__":
    sys.exit(main())