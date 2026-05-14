"""Ollama moondream captioning — async HTTP calls to local Ollama server.

Requires `ollama serve` running on localhost:11434 with moondream model pulled.
Falls back gracefully if Ollama is not available.
"""

import base64
import json
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE = "http://localhost:11434"
CAPTION_MODEL = "moondream"
TAG_MODEL = "moondream"

CAPTION_PROMPT = "Describe this image in one detailed sentence."
TAG_PROMPT = (
    "List 5-10 descriptive tags for this image as a JSON array of strings. "
    "Include objects, scene, mood, colors, and activities. "
    "Return ONLY the JSON array, nothing else. Example: [\"sunset\", \"beach\", \"people\"]"
)


async def check_ollama_available() -> bool:
    """Check if Ollama is running and the model is available."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{OLLAMA_BASE}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                names = [m.get("name", "").split(":")[0] for m in models]
                return CAPTION_MODEL in names
    except Exception:
        pass
    return False


async def generate_caption(image_path: Path) -> str | None:
    """Generate a caption for an image using Ollama moondream.

    Returns the caption string, or None if Ollama is unavailable.
    """
    image_b64 = _encode_image(image_path)
    if not image_b64:
        return None

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{OLLAMA_BASE}/api/generate",
                json={
                    "model": CAPTION_MODEL,
                    "prompt": CAPTION_PROMPT,
                    "images": [image_b64],
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 100},
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("response", "").strip()
    except Exception as e:
        logger.warning("Ollama caption failed for %s: %s", image_path.name, e)

    return None


async def generate_tags(image_path: Path) -> list[str]:
    """Extract tags from an image using Ollama moondream.

    Returns a list of tag strings, or empty list on failure.
    """
    image_b64 = _encode_image(image_path)
    if not image_b64:
        return []

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{OLLAMA_BASE}/api/generate",
                json={
                    "model": TAG_MODEL,
                    "prompt": TAG_PROMPT,
                    "images": [image_b64],
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 200},
                },
            )
            if resp.status_code == 200:
                raw = resp.json().get("response", "").strip()
                return _parse_tags(raw)
    except Exception as e:
        logger.warning("Ollama tags failed for %s: %s", image_path.name, e)

    return []


def _encode_image(image_path: Path) -> str | None:
    """Read image file and return base64 string."""
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.error("Failed to read image %s: %s", image_path, e)
        return None


def _parse_tags(raw: str) -> list[str]:
    """Robustly parse tags from LLM output. Handles JSON, comma-separated, etc."""
    # Try JSON array first
    try:
        # Find the JSON array in the response
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start >= 0 and end > start:
            tags = json.loads(raw[start:end])
            if isinstance(tags, list):
                return [str(t).strip().lower() for t in tags if str(t).strip()]
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: split by commas or newlines
    raw_clean = raw.strip("[]\"'")
    tags = []
    for sep in [",", "\n", ";", "•", "-"]:
        if sep in raw_clean:
            tags = [t.strip().strip("\"'").lower() for t in raw_clean.split(sep)]
            tags = [t for t in tags if t and len(t) < 50]
            if tags:
                return tags

    # Last resort: split by spaces if short enough
    words = raw_clean.split()
    if len(words) <= 10:
        return [w.strip("\"',.").lower() for w in words if len(w) > 2]

    return []
