"""Serve the browser test page and give it a LiveKit token.

Run from the repo root while the LiveKit server (see web/livekit.yaml) and
`src/agent.py dev` are up:

    uv run python web/server.py
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv
from livekit import api

load_dotenv(".env.local")

# Matches agent_name in src/agent.py.
AGENT_NAME = "parallel-search-agent"
PAGE = Path(__file__).with_name("index.html")


def connection_details() -> dict[str, str]:
    # A fresh room per session, so the token's dispatch below always applies.
    room = f"web-{secrets.token_hex(4)}"
    token = (
        api.AccessToken(
            os.environ.get("LIVEKIT_API_KEY", "devkey"),
            os.environ.get("LIVEKIT_API_SECRET", "secret"),
        )
        .with_identity(f"tester-{secrets.token_hex(3)}")
        .with_name("Web tester")
        .with_grants(api.VideoGrants(room_join=True, room=room))
        # The agent has a name, so LiveKit only sends it to rooms that ask for it.
        .with_room_config(
            api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)])
        )
        .to_jwt()
    )
    return {
        "serverUrl": os.environ.get("LIVEKIT_URL", "ws://127.0.0.1:7880"),
        "room": room,
        "token": token,
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/token":
            self._send(json.dumps(connection_details()).encode(), "application/json")
        elif self.path in ("/", "/index.html"):
            self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def _send(self, body: bytes, content_type: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("WEB_PORT", 8090))
    )
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Test page: http://localhost:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
