"""Tiny aiohttp server that serves the three ATS apply pages.

Used as a Playwright fixture: a real Chromium can navigate to
http://127.0.0.1:<port>/greenhouse/apply (or /lever/apply, /ashby/apply),
fill the form, and POST to /greenhouse/submit. The POST handler stores the
multipart body in `MockATSServer.submissions[platform]` for tests to assert on.

No live network. No outbound calls. Suitable for CI.
"""
from __future__ import annotations

import asyncio
import contextlib
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiohttp import web

PAGES_DIR = Path(__file__).parent


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@dataclass
class MockATSServer:
    port: int = 0
    submissions: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: {
        "greenhouse": [], "lever": [], "ashby": []
    })
    _runner: web.AppRunner | None = None
    _site: web.TCPSite | None = None

    def url_for(self, platform: str) -> str:
        return f"http://127.0.0.1:{self.port}/{platform}/apply"

    def submit_url_for(self, platform: str) -> str:
        return f"http://127.0.0.1:{self.port}/{platform}/submit"

    async def _serve_page(self, request: web.Request) -> web.Response:
        platform = request.match_info["platform"]
        html_path = PAGES_DIR / f"{platform}_apply.html"
        if not html_path.exists():
            return web.Response(status=404, text=f"unknown platform {platform}")
        return web.Response(body=html_path.read_bytes(), content_type="text/html")

    async def _accept_submission(self, request: web.Request) -> web.Response:
        platform = request.match_info["platform"]
        if platform not in self.submissions:
            return web.Response(status=404, text=f"unknown platform {platform}")
        reader = await request.multipart()
        captured: dict[str, Any] = {}
        while True:
            part = await reader.next()
            if part is None:
                break
            field_name = part.name or "_"
            if part.filename:
                blob = await part.read(decode=False)
                captured[field_name] = {
                    "filename": part.filename,
                    "size": len(blob),
                }
            else:
                captured[field_name] = (await part.text()).strip()
        self.submissions[platform].append(captured)
        return web.Response(text=f"<h1>Application received for {platform}</h1>", content_type="text/html")

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/{platform}/apply", self._serve_page)
        app.router.add_post("/{platform}/submit", self._accept_submission)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        if self.port == 0:
            self.port = _find_free_port()
        self._site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        await self._site.start()

    async def stop(self) -> None:
        if self._site is not None:
            await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = None
        self._site = None

    def reset(self) -> None:
        for k in self.submissions:
            self.submissions[k] = []


@contextlib.asynccontextmanager
async def running_server() -> Any:
    s = MockATSServer()
    await s.start()
    try:
        yield s
    finally:
        await s.stop()


def main() -> None:
    """Standalone runner: `python -m tests.fixtures.ats_pages.mock_server`"""
    async def _run() -> None:
        s = MockATSServer(port=8765)
        await s.start()
        print(f"mock ATS server listening on http://127.0.0.1:{s.port}")
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await s.stop()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
