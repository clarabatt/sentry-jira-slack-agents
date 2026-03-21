import json
import re


def extract_json_payload(text: str) -> dict:
    """Extract valid JSON from a text blob, including conversational prefixes and code fences."""
    text = (text or "").strip()

    # direct JSON object
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # first: fenced JSON code block (```json ...``` or ``` ... ```) and parse inner object
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if m:
        candidate = m.group(1).strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    # fallback: first { ... } block
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        candidate = m.group(0)
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    raise ValueError(f"Could not extract valid JSON payload from text: {text!r}")
