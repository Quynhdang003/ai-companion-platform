"""Download call artifacts from Dograh (behind an interface so tests can fake it)."""

from typing import Protocol

import httpx

from app.core.config import get_settings


class TranscriptFetchError(Exception):
    """Dograh or its storage didn't return the transcript (worth retrying)."""


class UntrustedURLError(Exception):
    """The link doesn't point at the configured Dograh API."""


class TranscriptSource(Protocol):
    async def fetch(self, url: str) -> str: ...


class DograhTranscriptSource:
    """Follows Dograh's public download link (302 to a signed storage URL)."""

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._prefix = base_url.rstrip("/") + "/"
        self._timeout = timeout_seconds
        self._transport = transport

    async def fetch(self, url: str) -> str:
        # The link comes from the webhook body: only follow it into our own Dograh.
        if not url.startswith(self._prefix):
            raise UntrustedURLError
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=True, transport=self._transport
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TranscriptFetchError(type(exc).__name__) from exc
        return response.content.decode("utf-8", errors="replace")


def get_transcript_source() -> TranscriptSource:
    return DograhTranscriptSource(get_settings().dograh_base_url)
