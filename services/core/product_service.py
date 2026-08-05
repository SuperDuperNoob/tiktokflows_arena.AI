"""Product service for managing products."""

from typing import Any, Dict, List, Optional

from services.repositories import ProductRepository, StockRepository
from services.models import Product


class ProductService:
    """Service for product management."""

    def __init__(self):
        self.product_repo = ProductRepository()
        self.stock_repo = StockRepository()

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

    def add_product(self, name: str, product_id: str, description: Optional[str] = None,
                    keywords: Optional[List[str]] = None,
                    yellow_bag_tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """Add a new product."""
        product = Product(
            name=name,
            product_id=product_id,
            description=description,
            keywords=keywords or [],
            yellow_bag_tags=yellow_bag_tags or [],
        )
        self.product_repo.save(product)
        return product.to_dict()

    def update_product(self, name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Update a product."""
        product = self.product_repo.get_by_name(name)
        if not product:
            return None
        
        for key, value in kwargs.items():
            if hasattr(product, key):
                setattr(product, key, value)
        
        self.product_repo.save(product)
        return product.to_dict()

    def get_stock_status(self) -> Dict[str, int]:
        """Get stock levels for all products."""
        return self.stock_repo.get_stock_counts()

    def check_low_stock(self, threshold: int = 5) -> List[str]:
        """Get list of products with low stock."""
        stock_counts = self.stock_repo.get_stock_counts()
        return [p for p, count in stock_counts.items() if count < threshold]