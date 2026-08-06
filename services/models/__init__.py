"""Domain models for the TikTok Auto-Posting Machine."""

from .upload_job import UploadJob, UploadJobStatus
from .video_asset import VideoAsset, VideoQuality
from .product import Product
from .caption import Caption, CaptionSource
from .compliance_result import ComplianceResult
from .upload_result import UploadResult
from .growth_report import GrowthReport
from .daily_summary import DailySummary
from .proxy_status import ProxyStatus, ProxyType

__all__ = [
    "UploadJob",
    "UploadJobStatus",
    "VideoAsset",
    "VideoQuality",
    "Product",
    "Caption",
    "CaptionSource",
    "ComplianceResult",
    "UploadResult",
    "GrowthReport",
    "DailySummary",
    "ProxyStatus",
    "ProxyType",
]