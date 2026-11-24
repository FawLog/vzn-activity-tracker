"""ASGI entrypoint used by Uvicorn."""

from .factory import create_app

app = create_app()
