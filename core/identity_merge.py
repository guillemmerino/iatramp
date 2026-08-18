"""Extension registry for consolidating domain data owned by other apps."""

from collections import OrderedDict


_person_merge_handlers = OrderedDict()


def register_person_merge_handler(name, handler):
    """Register one idempotent, app-owned person merge handler."""
    existing = _person_merge_handlers.get(name)
    if existing is not None and existing is not handler:
        raise RuntimeError(f"Ja hi ha un gestor de fusió registrat amb el nom {name!r}.")
    _person_merge_handlers[name] = handler


def run_person_merge_handlers(*, canonical, duplicate):
    """Run downstream merge handlers inside Core's outer transaction."""
    for handler in _person_merge_handlers.values():
        handler(canonical=canonical, duplicate=duplicate)


def registered_person_merge_handlers():
    """Expose immutable registry metadata for architecture tests and diagnostics."""
    return tuple(_person_merge_handlers)
