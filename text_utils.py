import json
from json_utils import extract_json_payload

def get_response_text(gen_response) -> str:
    """Safely extract text from a Gemini response without using the .text accessor."""
    for candidate in getattr(gen_response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        if content is None:
            continue
        if isinstance(content, str):
            return content.strip()
        for part in getattr(content, "parts", []) or []:
            if isinstance(part, str):
                return part.strip()
            text = getattr(part, "text", None)
            if text is not None:
                return text.strip()
    return ""

def clean_response_text(text):
    try:
        parsed = extract_json_payload(text)
        # normalize into compact JSON string for caller simplicity
        return json.dumps(parsed)
    except Exception:
        return text.strip()