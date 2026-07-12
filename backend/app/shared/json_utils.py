"""Generic JSON extraction helpers shared across layers."""
import json
import re


def _strip_markdown_fence_once(text: str) -> str:
    """Remove a single leading/trailing ``` fence without MULTILINE line damage."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    text = re.sub(r"^```(?:json|tsx?|javascript|typescript)?\s*\n?", "", text, count=1)
    text = re.sub(r"\n?```\s*$", "", text, count=1)
    return text.strip()


def extract_json_from_text(text: str):
    """Robustly extract the first valid JSON object from any model output."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty model output")

    # 1. Direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2. Strip one markdown fence (avoid MULTILINE ^/$ which can corrupt bodies)
    fenced = _strip_markdown_fence_once(text)
    try:
        return json.loads(fenced)
    except Exception:
        pass

    # Prefer bracket-matching on the fence-stripped body when present.
    search_in = fenced if fenced != text else text

    # 3. Find the outermost { ... } by bracket matching (handles large nested JSON)
    start = search_in.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model output")

    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(search_in[start:], start):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = search_in[start : i + 1]
                try:
                    return json.loads(candidate)
                except Exception:
                    break

    raise ValueError("No valid JSON object found in model output")
