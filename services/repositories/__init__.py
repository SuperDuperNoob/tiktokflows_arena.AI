"""Repository layer for database operations."""

from .base import BaseRepository
from .upload_repository import UploadRepository
from .product_repository import ProductRepository
from .caption_repository import CaptionRepository
from .analytics_repository import AnalyticsRepository
from .event_repository import EventRepository
from .stock_repository import StockRepository

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from db import Database

__all__ = [
    "BaseRepository",
    "UploadRepository",
    "ProductRepository",
    "CaptionRepository",
    "AnalyticsRepository",
    "EventRepository",
    "StockRepository",
    "Database",
]