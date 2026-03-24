#!/usr/bin/env bash
# Guardian One — Docker Quick Start
# Usage: ./scripts/docker-start.sh [up|down|logs|status|shell|pull-model]

set -euo pipefail

cd "$(dirname "$0")/.."

CMD="${1:-up}"

case "$CMD" in
  up)
    echo "Starting Guardian One..."
    docker compose up -d --build
    echo ""
    echo "  Guardian One is starting."
    echo "  Web Panel:   http://localhost:5100"
    echo "  Chat:        http://localhost:5100/chat"
    echo "  Health API:  http://localhost:5200/health"
    echo "  Ollama:      http://localhost:11434"
    echo ""
    echo "  Pull AI model:  ./scripts/docker-start.sh pull-model"
    echo "  View logs:      ./scripts/docker-start.sh logs"
    ;;

  down)
    echo "Stopping Guardian One..."
    docker compose down
    ;;

  logs)
    docker compose logs -f guardian
    ;;

  status)
    echo "=== Container Status ==="
    docker compose ps
    echo ""
    echo "=== Guardian Health ==="
    curl -s http://localhost:5200/health 2>/dev/null | python3 -m json.tool || echo "Guardian not responding"
    echo ""
    echo "=== Ollama Status ==="
    curl -s http://localhost:11434/api/tags 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
models = data.get('models', [])
if models:
    for m in models:
        print(f\"  {m['name']}\")
else:
    print('  No models pulled. Run: ./scripts/docker-start.sh pull-model')
" 2>/dev/null || echo "  Ollama not responding"
    ;;

  shell)
    docker compose exec guardian bash
    ;;

  pull-model)
    MODEL="${2:-llama3}"
    echo "Pulling $MODEL into Ollama..."
    docker compose exec ollama ollama pull "$MODEL"
    echo "Done. $MODEL is ready."
    ;;

  cli)
    shift
    docker compose exec guardian python main.py "$@"
    ;;

  *)
    echo "Usage: $0 [up|down|logs|status|shell|pull-model|cli]"
    echo ""
    echo "  up          Start Guardian One + Ollama"
    echo "  down        Stop everything"
    echo "  logs        Follow Guardian logs"
    echo "  status      Show container + health status"
    echo "  shell       Open bash in Guardian container"
    echo "  pull-model  Pull Ollama model (default: llama3)"
    echo "  cli ...     Run any Guardian CLI command"
    echo ""
    echo "Examples:"
    echo "  $0 up"
    echo "  $0 pull-model llama3"
    echo "  $0 cli --summary"
    echo "  $0 cli --dashboard"
    exit 1
    ;;
esac
