"""HTTP API for remote assistant deployments."""

from .app import create_app

__all__ = ["create_app"]