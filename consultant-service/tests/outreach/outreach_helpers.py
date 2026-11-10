"""Shapes the outreach tests share."""


def reply(content: str, cited: list[str] = ()) -> dict:
    """A model reply as OpenRouter shapes it, citing `cited`."""
    return {"choices": [{"message": {"content": content, "annotations": [
        {"type": "url_citation", "url_citation": {"url": u}} for u in cited]}}], "usage": {}}
