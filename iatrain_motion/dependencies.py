"""Downstream dependency registry that keeps iatrain_motion free of reverse imports."""

from collections import OrderedDict


_handlers = OrderedDict()


def register_motion_dependency_handler(name, handler):
    if name in _handlers and _handlers[name] is not handler:
        raise RuntimeError(f"Ja existeix un gestor de dependències de moviment per a {name}.")
    _handlers[name] = handler


def collect_motion_dependency_issues(*, instance, target_status):
    issues = []
    for name, handler in _handlers.items():
        for issue in handler(instance=instance, target_status=target_status) or ():
            issues.append(f"{name}: {issue}")
    return issues

