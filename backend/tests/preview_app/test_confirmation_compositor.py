from app.application.preview_app.utility_compositor import (
    compose_utility_page_tsx,
    default_utility_content,
    infer_utility_workspace_type,
)


def test_infer_confirmation_from_waitlist_path():
    assert (
        infer_utility_workspace_type("/waitlist-confirmation", "Waitlist Confirmed")
        == "confirmation"
    )


def test_compose_confirmation_uses_confirm_stage():
    content = default_utility_content(
        "confirmation", brand_name="Clay", title="You're on the Waitlist"
    )
    tsx = compose_utility_page_tsx(
        file_path="src/pages/WaitlistConfirmationPage.tsx",
        route={"path": "/waitlist-confirmation", "title": "Waitlist"},
        content=content,
        brand_name="Clay",
        workspace_type="confirmation",
    )
    assert "ConfirmStage" in tsx
    assert "md:grid-cols-2" not in tsx
