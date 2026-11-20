#!/bin/zsh
# Starts Cognee vendor memory: a local embedding endpoint (app/embed.py) plus the memory service on :8766.
# Runs in its own Python environment (~/hackathons/cognee-env) so Cognee can't change the relay's libraries.
cd "$(dirname "$0")/.."
set -a; source .env; set +a
export LLM_PROVIDER=anthropic LLM_MODEL=anthropic/claude-haiku-4-5 LLM_API_KEY="$ANTHROPIC_API_KEY"
export EMBEDDING_PROVIDER=openai_compatible EMBEDDING_MODEL=open-union-hash-384 \
       EMBEDDING_ENDPOINT=http://127.0.0.1:8765/v1 EMBEDDING_API_KEY=. EMBEDDING_DIMENSIONS=384
export REQUIRE_AUTHENTICATION=false ENABLE_BACKEND_ACCESS_CONTROL=false
~/hackathons/union-env/bin/python scripts/local_embed_server.py &
EMBED_PID=$!
trap 'kill $EMBED_PID 2>/dev/null' EXIT
~/hackathons/cognee-env/bin/python scripts/memory_service.py
