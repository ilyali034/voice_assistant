import asyncio
import ipaddress
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .assistant_service import ResponseEngine


class RemoteResponseEngine:
    """Send text requests to a remote assistant API as a response engine."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 60.0,
    ) -> None:
        parsed_url = urlparse(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("base_url must be an absolute HTTP or HTTPS URL")
        if parsed_url.username or parsed_url.password:
            raise ValueError("base_url must not contain embedded credentials")
        try:
            parsed_url.port
        except ValueError as error:
            raise ValueError("base_url contains an invalid port") from error

        hostname = parsed_url.hostname or ""
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback = hostname.casefold() == "localhost"
        if parsed_url.scheme == "http" and not is_loopback:
            raise ValueError("HTTPS is required for non-local backend URLs")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if not api_key.strip():
            raise ValueError("api_key must not be empty")

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.timeout = timeout

    async def handle(self, request: str) -> str:
        """Send one request without blocking the caller's event loop."""
        body = json.dumps({"request": request}).encode("utf-8")
        remote_request = Request(
            f"{self.base_url}/v1/requests",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            response_data = await asyncio.to_thread(self._post, remote_request)
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Assistant backend returned HTTP {error.code}: "
                f"{details or error.reason}"
            ) from error
        except (URLError, TimeoutError) as error:
            raise RuntimeError(
                f"Could not connect to assistant backend at {self.base_url}."
            ) from error
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("Assistant backend returned invalid JSON.") from error

        response = response_data.get("response")
        if not isinstance(response, str):
            raise RuntimeError("Assistant backend response has no string 'response'.")
        return response.strip()

    def _post(self, request: Request) -> dict[str, Any]:
        with urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, dict):
            raise RuntimeError("Assistant backend returned an invalid payload.")
        return data