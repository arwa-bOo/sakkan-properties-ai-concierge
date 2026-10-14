"""Thin Gemini wrapper (generation + embeddings) with a deterministic MOCK_MODE."""
import hashlib
import json
import math
import re
import time

from . import settings

_client = None
_STOP = {"a", "an", "the", "to", "for", "of", "in", "and", "is", "are", "our", "with", "on", "at", "what", "how", "do", "we", "it", "by"}


def _gemini():
    global _client
    if _client is None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is missing. Put it in .env or run with MOCK_MODE=true.")
        from google import genai
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def generate(prompt: str, system: str | None = None, json_mode: bool = False, temperature: float = 0.2) -> str:
    if settings.MOCK_MODE:
        return ""
    from google.genai import types
    cfg = types.GenerateContentConfig(
        system_instruction=system, temperature=temperature,
        response_mime_type="application/json" if json_mode else None)
    last = None
    for attempt in range(4):
        try:
            return _gemini().models.generate_content(model=settings.GEMINI_MODEL, contents=prompt, config=cfg).text or ""
        except Exception as e:
            code = getattr(e, "code", None)
            if code in (400, 401, 403, 404):      # not retryable: bad key / model name -> fail fast with a clear message
                raise RuntimeError(f"Gemini rejected the request ({code}). Check GEMINI_API_KEY and GEMINI_MODEL ('{settings.GEMINI_MODEL}'): {e}")
            last = e                              # 429 / 5xx: free-tier rate limit, wait longer each time
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Gemini generate failed: {last}")


def extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    s, e = text.find("{"), text.rfind("}")
    return json.loads(text[s:e + 1])


def _hash_embed(text: str) -> list[float]:
    """Mock embedding: hashed bag of unigrams+bigrams. Deterministic, offline, lexically meaningful."""
    toks = [re.sub(r"(ing|ed|es|s)$", "", t) if len(t) > 4 else t for t in re.findall(r"\w+", text.lower()) if t not in _STOP]
    grams = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
    v = [0.0] * settings.EMBED_DIM
    for g in grams:
        h = int(hashlib.md5(g.encode()).hexdigest(), 16)
        v[h % settings.EMBED_DIM] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def embed(texts: list[str], task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    if settings.MOCK_MODE:
        return [_hash_embed(t) for t in texts]
    from google.genai import types
    out: list[list[float]] = []
    for i in range(0, len(texts), 16):
        batch = texts[i:i + 16]
        for attempt in range(6):
            try:
                r = _gemini().models.embed_content(
                    model=settings.EMBED_MODEL, contents=batch,
                    config=types.EmbedContentConfig(task_type=task, output_dimensionality=settings.EMBED_DIM))
                for e in r.embeddings:
                    n = math.sqrt(sum(x * x for x in e.values)) or 1.0
                    out.append([x / n for x in e.values])
                break
            except Exception as ex:
                if attempt == 5:
                    raise RuntimeError(f"Gemini embed failed: {ex}")
                time.sleep(8 * (attempt + 1))
        time.sleep(0.3)
    return out
