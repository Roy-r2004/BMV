"""Generic JSON extraction helpers shared across layers."""
import json
import re


def extract_json_from_text(text: str):
    """Robustly extract the first valid JSON object from any model output."""
    text = text.strip()

    # 1. Direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2. Strip markdown fence then parse
    fenced = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    fenced = re.sub(r"\s*```\s*$", "", fenced, flags=re.MULTILINE).strip()
    try:
        return json.loads(fenced)
    except Exception:
        pass

    # 3. Find the outermost { ... } by bracket matching (handles large nested JSON)
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model output")

    depth = 0
    in_str = False
    escape = False
    for i, ch in enumerate(text[start:], start):
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
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except Exception:
                    break

    raise ValueError("No valid JSON object found in model output")
