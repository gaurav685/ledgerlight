"""robots.txt compliance check used before every fetch."""

from __future__ import annotations

import urllib.robotparser
from urllib.parse import urlparse

import httpx


class RobotsCache:
    """Per-host robots.txt parsers, fetched lazily and cached for the process lifetime."""

    def __init__(self, user_agent: str, client: httpx.Client) -> None:
        self._user_agent = user_agent
        self._client = client
        self._parsers: dict[str, urllib.robotparser.RobotFileParser] = {}

    def _get_parser(self, url: str) -> urllib.robotparser.RobotFileParser:
        parsed = urlparse(url)
        host_key = f"{parsed.scheme}://{parsed.netloc}"
        if host_key not in self._parsers:
            parser = urllib.robotparser.RobotFileParser()
            robots_url = f"{host_key}/robots.txt"
            try:
                resp = self._client.get(
                    robots_url, headers={"User-Agent": self._user_agent}, timeout=10.0
                )
                if resp.status_code == 200:
                    parser.parse(resp.text.splitlines())
                else:
                    # No robots.txt (or unreachable) is treated as "allow" per
                    # standard robots.txt convention, not as a licence to ignore ToS.
                    parser.parse([])
            except httpx.HTTPError:
                parser.parse([])
            self._parsers[host_key] = parser
        return self._parsers[host_key]

    def is_allowed(self, url: str) -> bool:
        parser = self._get_parser(url)
        return parser.can_fetch(self._user_agent, url)
