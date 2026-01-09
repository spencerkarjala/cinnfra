import importlib
import pkgutil
from pathlib import Path

from .base import BaseHandler


def discover_handlers() -> list[BaseHandler]:
    handlers = []
    package_dir = Path(__file__).parent

    for _, module_name, _ in pkgutil.iter_modules([str(package_dir)]):
        if module_name == "base":
            continue
        module = importlib.import_module(f".{module_name}", package=__package__)
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseHandler)
                and attr is not BaseHandler
            ):
                handlers.append(attr())
    return handlers


HANDLERS: list[BaseHandler] = discover_handlers()


def get_handler(url: str) -> BaseHandler | None:
    for handler in HANDLERS:
        if handler.can_handle(url):
            return handler
    return None
