from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class AssistantContext:
    """Module-owned content and capabilities consumed by the core assistant shell."""

    module: str
    messages: Mapping[str, Any] = field(default_factory=dict)
    initial_topic: str = "welcome"
    chat_url: str = ""


AssistantProvider = Callable[[Any], AssistantContext | None]
_providers: list[AssistantProvider] = []


def register_assistant_provider(provider: AssistantProvider) -> None:
    """Register a module provider once; providers are queried in registration order."""

    if provider not in _providers:
        _providers.append(provider)


def get_assistant_context(request: Any) -> AssistantContext | None:
    """Return the first module context matching the current request."""

    for provider in tuple(_providers):
        context = provider(request)
        if context is not None:
            return context
    return None
