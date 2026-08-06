"""Product service for managing products."""

from typing import Any, Dict, List, Optional

from services.repositories import ProductRepository, StockRepository
from services.models import Product
from services.infrastructure.logging import get_logger

logger = get_logger(__name__)


class ProductService:
    """Service for product management."""

    def __init__(self, db_path: str):
        self.product_repo = ProductRepository(db_path)
        self.stock_repo = StockRepository(db_path)

    def get_all_products(self) -> List[Dict[str, Any]]:
        """Get all products with stock info."""
        products = self.product_repo.get_all()
        stock_counts = self.stock_repo.get_stock_counts()

        result = []
        for p in products:
            p.stock_count = stock_counts.get(p.name, 0)
            result.append(p.to_dict())
        return result

    def get_product(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a single product by name."""
        product = self.product_repo.get_by_name(name)
        if product:
            stock_counts = self.stock_repo.get_stock_counts()
            product.stock_count = stock_counts.get(product.name, 0)
            return product.to_dict()
        return None

    def save_product(self, product: Product) -> None:
        """Save a product."""
        self.product_repo.save(product)
        logger.info("Product saved: %s", product.name)