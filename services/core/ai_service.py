"""AI service for AI-powered features."""

from typing import Any, Dict, List, Optional

from services.infrastructure.ai_adapter import AIAdapter


class AIService:
    """Service for AI-powered features."""

    def __init__(self):
        self.ai_adapter = AIAdapter()

    def generate_captions(self, product_name: str, product_config: Dict[str, Any]) -> List[str]:
        """Generate captions for a product."""
        return self.ai_adapter.generate_captions(product_name, product_config)

    def generate_strategy(self, products_config: Dict[str, Any]) -> Optional[str]:
        """Generate strategy report."""
        return self.ai_adapter.generate_strategy(products_config)

    def check_compliance(self, caption_text: str) -> Dict[str, Any]:
        """Check caption compliance using AI."""
        return self.ai_adapter.check_compliance(caption_text)

    def rewrite_caption(self, caption_text: str) -> Optional[str]:
        """Rewrite a caption to be compliant."""
        return self.ai_adapter.rewrite_caption(caption_text)