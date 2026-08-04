"""
AI Caption & Strategy Engine

Generates captions and strategy recommendations using an OpenAI-compatible API.
Only triggered manually via Telegram /growth command to control costs.

Two modes:
1. Caption generation — cheap model, generates 10 captions per product
2. Strategy generation — stronger model, generates a markdown report
"""
import json
import logging
from typing import List, Optional

import httpx

from db import Database

logger = logging.getLogger(__name__)


class AIEngine:
    """AI-powered caption and strategy generator."""

    def __init__(self, config: dict, db: Database):
        self.base_url = config.get("base_url", "").rstrip("/")
        self.api_key = config.get("api_key", "")
        self.caption_model = config.get("caption_model", "gpt-3.5-turbo")
        self.strategy_model = config.get("strategy_model", "gpt-4")
        self.max_caption_tokens = config.get("max_caption_tokens", 300)
        self.max_strategy_tokens = config.get("max_strategy_tokens", 1000)
        self.db = db

        if not self.base_url or self.base_url == "https://your-openai-compatible-endpoint.com/v1":
            logger.warning("AI base_url not configured")

    def generate_captions(self, product_name: str, product_config: dict) -> List[str]:
        """
        Generate 10 caption ideas for a product.

        Args:
            product_name: Name of the product
            product_config: Product config from config.yaml (description, keywords)

        Returns:
            List of 10 caption strings
        """
        # Gather context
        top_captions = self._get_top_captions(product_name)
        competitor_posts = self._get_competitor_context()

        system_prompt = self._build_caption_system_prompt()
        user_prompt = self._build_caption_user_prompt(
            product_name, product_config, top_captions, competitor_posts
        )

        response = self._call_api(
            model=self.caption_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=self.max_caption_tokens,
            temperature=0.8,
        )

        if not response:
            return []

        captions = self._parse_caption_response(response)

        # Log the AI call
        self.db.log_event(
            "AI_CALL",
            f"Generated {len(captions)} captions for {product_name}",
            metadata={
                "type": "caption_generation",
                "product": product_name,
                "model": self.caption_model,
                "captions_count": len(captions),
            }
        )

        return captions

    def generate_strategy(self, products_config: dict) -> Optional[str]:
        """
        Generate a strategic recommendation report.

        Args:
            products_config: Full products config from config.yaml

        Returns:
            Markdown-formatted strategy report string
        """
        # Gather performance data
        performance = self.db.get_performance_summary(days=7)
        competitor_data = self.db.get_recent_competitor_data(days=7)
        stock_counts = self.db.get_raw_stock_counts()
        products_due = self.db.get_products_due_next()

        system_prompt = self._build_strategy_system_prompt()
        user_prompt = self._build_strategy_user_prompt(
            performance, competitor_data, stock_counts, products_due, products_config
        )

        response = self._call_api(
            model=self.strategy_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=self.max_strategy_tokens,
            temperature=0.6,
        )

        if not response:
            return None

        # Log the AI call
        self.db.log_event(
            "AI_CALL",
            "Generated strategy report",
            metadata={
                "type": "strategy_generation",
                "model": self.strategy_model,
            }
        )

        return response

    def _call_api(self, model: str, system_prompt: str, user_prompt: str,
                  max_tokens: int, temperature: float = 0.7) -> Optional[str]:
        """Call the OpenAI-compatible API."""
        if not self.base_url or not self.api_key:
            logger.error("AI API not configured (base_url or api_key missing)")
            return None

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]

            # Log token usage
            usage = data.get("usage", {})
            logger.info(
                f"AI call ({model}): {usage.get('prompt_tokens', '?')} prompt + "
                f"{usage.get('completion_tokens', '?')} completion = "
                f"{usage.get('total_tokens', '?')} total tokens"
            )
            return content

        except httpx.HTTPStatusError as e:
            logger.error(f"AI API error ({e.response.status_code}): {e.response.text[:300]}")
            return None
        except Exception as e:
            logger.error(f"AI API call failed: {e}")
            return None

    def _get_top_captions(self, product_name: str) -> List[dict]:
        """Get top 5 performing captions for this product from DB."""
        captions = self.db.get_caption_pool_for_product(product_name)
        # Sort by times_used descending (most used = best performing proxy)
        captions.sort(key=lambda c: c.get("times_used", 0), reverse=True)
        return captions[:5]

    def _get_competitor_context(self) -> List[dict]:
        """Get top competitor posts for context."""
        return self.db.get_top_competitor_posts(min_views=5000, limit=10)

    def _build_caption_system_prompt(self) -> str:
        return """You are an expert TikTok Shop copywriter specializing in Bahasa Malaysia (Malaysian Malay).
You write engaging, casual, conversational captions for TikTok Shop product videos.

RULES:
1. Language: Bahasa Malaysia, casual/conversational tone (not formal)
2. Each caption must be UNDER 150 characters (including hashtags)
3. Each caption must naturally include 2-3 relevant hashtags
4. NO medical claims (sembuh, rawat, ubat, penawar, etc.)
5. NO price guarantees (paling murah, termurah, etc.)
6. NO superlatives (terbaik di dunia, no.1, etc.)
7. NO guaranteed results (jamin putih, jamin cantik, etc.)
8. Use soft, aspirational language instead of claims
9. Make it feel authentic, like a real person sharing, not an ad
10. Include trending TikTok-style phrasing

RESPOND WITH ONLY a JSON array of strings, e.g.:
["caption 1 with #hashtag", "caption 2 #tag1 #tag2", ...]

Do not include any other text, explanation, or markdown formatting."""

    def _build_caption_user_prompt(self, product_name: str, product_config: dict,
                                   top_captions: list, competitor_posts: list) -> str:
        description = product_config.get("description", "Product")
        keywords = ", ".join(product_config.get("keywords", []))

        prompt = f"""Generate 10 TikTok Shop captions for this product:

Product: {product_name}
Description: {description}
Keywords: {keywords}

"""
        if top_captions:
            prompt += "\nMy top performing captions so far:\n"
            for c in top_captions:
                prompt += f"- \"{c['caption_text']}\" (used {c.get('times_used', 0)} times)\n"

        if competitor_posts:
            prompt += "\nWhat's working for competitors (high-view posts):\n"
            for p in competitor_posts[:5]:
                hashtags = p.get("hashtags", "[]")
                if isinstance(hashtags, str):
                    try:
                        hashtags = json.loads(hashtags)
                    except:
                        hashtags = []
                prompt += f"- {p.get('caption_text', '')[:100]} ({p.get('view_count', 0)} views, hashtags: {', '.join(hashtags[:3])})\n"

        prompt += "\nGenerate 10 fresh captions. Remember: under 150 chars each, 2-3 hashtags, casual BM, no banned phrases."
        return prompt

    def _build_strategy_system_prompt(self) -> str:
        return """You are a TikTok Shop growth strategist. Analyze the data provided and generate a strategic action plan.

Your analysis should cover:
1. Which product to push hardest this week and why
2. What content angles are working for competitors that I'm not using
3. Recommended posting time adjustments
4. 3 specific strategic actions to take immediately

Format as clean Markdown. Be specific and actionable — no generic advice.
Base recommendations on the actual data provided, not assumptions.
Keep the total report under 800 words."""

    def _build_strategy_user_prompt(self, performance: dict, competitor_data: list,
                                    stock_counts: dict, products_due: list,
                                    products_config: dict) -> str:
        prompt = "## My Performance (Last 7 Days)\n\n"

        if performance.get("by_product"):
            for p in performance["by_product"]:
                prompt += (f"- **{p['product_name']}**: {p['post_count']} posts, "
                          f"{p['total_views']} total views, "
                          f"avg {p['avg_views']:.0f} views/post\n")
        else:
            prompt += "No posts in the last 7 days.\n"

        prompt += f"\nPosts today: {performance.get('today_count', 0)}\n"

        prompt += "\n## Current Stock Levels\n\n"
        for product, count in stock_counts.items():
            prompt += f"- {product}: {count} raw videos remaining\n"

        prompt += "\n## Products Due Next (by posting priority)\n\n"
        for p in products_due[:5]:
            prompt += (f"- {p['product_name']}: {p['stock_count']} stock, "
                      f"last posted: {p.get('last_posted', 'never')}\n")

        if competitor_data:
            prompt += "\n## Competitor Activity (Last 7 Days)\n\n"
            # Group by handle
            by_handle = {}
            for c in competitor_data:
                handle = c.get("competitor_handle", "unknown")
                by_handle.setdefault(handle, []).append(c)

            for handle, posts in by_handle.items():
                viral = [p for p in posts if p.get("view_count", 0) >= 10000]
                prompt += f"- **{handle}**: {len(posts)} posts, {len(viral)} viral (10K+ views)\n"
                if viral:
                    top = viral[0]
                    prompt += f"  - Top: {top.get('caption_text', '')[:80]}... ({top.get('view_count', 0)} views)\n"

        prompt += "\nBased on this data, generate a strategic action plan."
        return prompt

    def _parse_caption_response(self, response: str) -> List[str]:
        """Parse the AI response into a list of caption strings."""
        # Try to extract JSON array from response
        text = response.strip()

        # Remove markdown code blocks if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])

        # Try direct JSON parse
        try:
            captions = json.loads(text)
            if isinstance(captions, list):
                return [str(c).strip() for c in captions if str(c).strip()]
        except json.JSONDecodeError:
            pass

        # Try to find JSON array in the text
        import re
        match = re.search(r'\[.*\]', text, re.DOTALL)
        if match:
            try:
                captions = json.loads(match.group())
                if isinstance(captions, list):
                    return [str(c).strip() for c in captions if str(c).strip()]
            except json.JSONDecodeError:
                pass

        # Fallback: split by newlines, strip quotes/bullets
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        captions = []
        for line in lines:
            # Remove bullet points, numbers, quotes
            cleaned = re.sub(r'^[\d\.\-\*\"]+\s*', '', line).strip().strip('"\'')
            if cleaned and len(cleaned) > 10:
                captions.append(cleaned)

        return captions[:10]  # cap at 10
