"""Product repository for managing products."""

from typing import Any, Dict, List, Optional
import json
from scripts.config import get_config

from .base import BaseRepository
from services.models.product import Product


class ProductRepository(BaseRepository):
    """Repository for product operations."""

    def __init__(self, db_path: str):
        super().__init__(db_path)

    def get_table_name(self) -> str:
        return "products"  # This is a virtual table, data comes from products.json

    def get_all(self) -> List[Product]:
        """Get all products from products.json."""
        cfg = get_config()
        products_file = cfg.get("google_drive", "products_file", "content/products.json")
        
        try:
            with open(products_file, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []
        
        products = []
        for name, product_data in data.items():
            if isinstance(product_data, dict):
                product = Product(
                    name=name,
                    product_id=product_data.get("id", ""),
                    titles=product_data.get("titles", []),
                    captions=product_data.get("captions", []),
                    description=product_data.get("description"),
                    keywords=product_data.get("keywords", []),
                    yellow_bag_tags=product_data.get("yellow_bag_tags", []),
                    stock_count=0,  # Will be populated from DB
                )
            else:
                product = Product(
                    name=name,
                    product_id=str(product_data),
                    stock_count=0,
                )
            products.append(product)
        return products

    def get_by_name(self, name: str) -> Optional[Product]:
        """Get product by name."""
        products = self.get_all()
        for p in products:
            if p.name == name:
                return p
        return None

    def save(self, product: Product) -> None:
        """Save product to products.json."""
        cfg = get_config()
        products_file = cfg.get("google_drive", "products_file", "content/products.json")
        
        # Load existing
        try:
            with open(products_file, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}
        
        # Update
        data[product.name] = {
            "id": product.product_id,
            "titles": product.titles,
            "captions": product.captions,
            "description": product.description,
            "keywords": product.keywords,
            "yellow_bag_tags": product.yellow_bag_tags,
        }
        
        # Save
        with open(products_file, "w") as f:
            json.dump(data, f, indent=2)