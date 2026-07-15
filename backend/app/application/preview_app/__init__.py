__all__ = ["generate_preview_app"]


def __getattr__(name: str):
    """Load the heavyweight pipeline only when the package export is requested.

    Preview helpers are imported by product-planning services. Eagerly importing
    ``pipeline`` here makes those helpers recurse back into the planner before it
    has finished initializing.
    """

    if name == "generate_preview_app":
        from app.application.preview_app.pipeline import generate_preview_app

        return generate_preview_app
    raise AttributeError(name)
