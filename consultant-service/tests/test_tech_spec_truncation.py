"""A module's technical spec is retried when the model is cut off by the cap.

Run 59 asked for infrastructure modules whose data models, APIs and
integrations ran past the 3,200-token budget. The JSON came back cut off
mid-string — `Unterminated string starting at: line 223 column 5 (char 12242)`
— `extract_json_from_text` could not parse the wreckage, and the whole
engagement failed after $0.18. A denser module needs a bigger budget, not a
parse error.
"""
import inspect

from app.pipeline import decompose


def test_the_budget_ladder_grows():
    budgets = decompose.TECH_SPEC_BUDGETS
    assert len(budgets) >= 2, "there is no second attempt for a truncated spec"
    assert list(budgets) == sorted(budgets), "the ladder must grow, not shrink"
    assert budgets[-1] >= 2 * budgets[0], \
        "the retry budget must be materially larger or the retry buys nothing"


def test_a_truncated_spec_is_retried_before_it_is_parsed():
    """The retry is driven by the model's own finish_reason, not by guessing
    from the parse failure."""
    src = inspect.getsource(decompose)
    assert "for budget in TECH_SPEC_BUDGETS:" in src
    assert 'choice.get("finish_reason") != "length"' in src, \
        "truncation must be detected from finish_reason"
    loop = src.index("for budget in TECH_SPEC_BUDGETS:")
    parse = src.index("extract_json_from_text(choice", loop)
    brk = src.index("break", loop)
    assert brk < parse, "the loop must finish before the content is parsed"


def test_the_ladder_stops_as_soon_as_the_model_completes():
    """Simulates the loop: a complete first answer must not spend a second call."""
    calls = []

    def fake_chat(budget: int, finish: str):
        calls.append(budget)
        return {"choices": [{"finish_reason": finish, "message": {"content": "{}"}}]}

    # complete on the first attempt -> one call
    calls.clear()
    for budget in decompose.TECH_SPEC_BUDGETS:
        body = fake_chat(budget, "stop")
        if body["choices"][0].get("finish_reason") != "length":
            break
    assert calls == [decompose.TECH_SPEC_BUDGETS[0]]

    # cut off every time -> every rung tried, largest last
    calls.clear()
    for budget in decompose.TECH_SPEC_BUDGETS:
        body = fake_chat(budget, "length")
        if body["choices"][0].get("finish_reason") != "length":
            break
    assert calls == list(decompose.TECH_SPEC_BUDGETS)
