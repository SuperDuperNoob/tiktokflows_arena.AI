"""AI adapter for AI-powered features."""

from typing import Any, Dict, List, Optional
import requests
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts"))
from config import get_config


class AIAdapter:
    """Adapter for AI-powered features."""

    def __init__(self):
        self.config = get_config()
        self.ai_config = self.config.get_section("ai")

    def _ai_available(self) -> bool:
        return bool(
            self.ai_config.get("enable_ai", False)
            and self.ai_config.get("api_key")
            and self.ai_config.get("base_url")
        )

    def call_ai(self, prompt: str, system: str, model: Optional[str] = None,
                max_tokens: int = 1000, temperature: float = 0.7) -> Optional[str]:
        """Call the AI API."""
        if not self._ai_available():
            return None
        
        base = self.ai_config.get("base_url", "").rstrip("/")
        api_key = self.ai_config.get("api_key", "")
        model = model or self.ai_config.get("model", "auto")
        timeout = self.ai_config.get("timeout_seconds", 45)
        retries = self.ai_config.get("retries", 2)
        
        for attempt in range(1, retries + 1):
            try:
                resp = requests.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}",
                             "Content-Type": "application/json"},
                    json={"model": model,
                          "messages": [{"role": "system", "content": system},
                                       {"role": "user", "content": prompt}],
                          "temperature": temperature,
                          "max_tokens": max_tokens},
                    timeout=timeout)
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
                if 400 <= resp.status_code < 500 and resp.status_code != 429:
                    return None
            except Exception as e:
                pass
        return None

    def generate_captions(self, product_name: str, product_config: Dict[str, Any]) -> List[str]:
        """Generate captions for a product."""
        system = """You are an expert TikTok Shop copywriter specializing in Bahasa Malaysia.
Generate 10 engaging, casual captions. Each under 150 chars with 2-3 hashtags.
NO medical claims, price guarantees, superlatives, or guaranteed results."""
        
        description = product_config.get("description", "Product")
        keywords = ", ".join(product_config.get("keywords", []))
        
        prompt = f"""Generate 10 TikTok Shop captions for:
Product: {product_name}
Description: {description}
Keywords: {keywords}

Rules: Under 150 chars, 2-3 hashtags, casual BM, no banned phrases.
Return ONLY a JSON array of strings."""
        
        response = self.call_ai(prompt, system, max_tokens=300, temperature=0.8)
        if not response:
            return []
        
        # Parse JSON response
        import json
        try:
            captions = json.loads(response)
            if isinstance(captions, list):
                return [str(c).strip() for c in captions if str(c).strip()]
        except json.JSONDecodeError:
            pass
        return []

    def generate_strategy(self, products_config: Dict[str, Any]) -> Optional[str]:
        """Generate strategy report."""
        system = "You are a TikTok Shop Malaysia growth strategist. Analyze data and generate a strategic action plan in Markdown."
        prompt = "Generate a strategic action plan based on the data."
        
        return self.call_ai(prompt, system, max_tokens=1000, temperature=0.6)

    def check_compliance(self, caption_text: str) -> Dict[str, Any]:
        """Check caption compliance using AI."""
        if not self._ai_available():
            return {"is_compliant": True, "violations": [], "severity": "none"}
        
        system = """You are a TikTok Shop Malaysia compliance officer.
Review captions for medical claims, price guarantees, superlatives, guaranteed results.
Reply with ONLY JSON: {"is_compliant": bool, "violations": [...], "rewritten_caption": "..."}"""
        
        response = self.call_ai(f'Analyze: "{caption_text}"', system, max_tokens=500, temperature=0.1)
        if not response:
            return {"is_compliant": True, "violations": [], "severity": "none"}
        
        import json
        try:
            start, end = response.find("{"), response.rfind("}")
            if start != -1 and end > start:
                data = json.loads(response[start:end+1])
                return data if isinstance(data, dict) else {"is_compliant": True, "violations": []}
        except json.JSONDecodeError:
            pass
        return {"is_compliant": True, "violations": [], "severity": "none"}

    def rewrite_caption(self, caption_text: str) -> Optional[str]:
        """Rewrite a caption to be compliant."""
        result = self.check_compliance(caption_text)
        return result.get("rewritten_caption")