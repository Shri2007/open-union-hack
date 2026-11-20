"""Tiny OpenAI-compatible /v1/embeddings server backed by app/embed.py (local hashed embedding, 384 dims).

Lets Cognee reuse the repo's own embedding with no model download and no API key:
  EMBEDDING_PROVIDER=openai_compatible EMBEDDING_ENDPOINT=http://127.0.0.1:8765/v1 EMBEDDING_DIMENSIONS=384
Run: python scripts/local_embed_server.py [port]
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.embed import DIMS, embed  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        inp = body.get("input", [])
        inputs = [inp] if isinstance(inp, str) else inp
        data = [{"object": "embedding", "index": i, "embedding": embed(t)} for i, t in enumerate(inputs)]
        out = json.dumps({"object": "list", "data": data, "model": "open-union-hash-384",
                          "usage": {"prompt_tokens": 0, "total_tokens": 0}}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"local embedding server on :{port} ({DIMS} dims)", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
