from .assistant import get_assistant_context


def assistant(request):
    """Expose a neutral assistant contract without importing feature modules."""

    return {"assistant_context": get_assistant_context(request)}
