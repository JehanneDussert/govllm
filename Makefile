.PHONY: help dev prod down build rebuild logs ps \
        pull-models \
        flush-redis flush-judge flush-scores \
        benchmark benchmark-generate benchmark-evaluate \
        gt-seed gt-status gt-kill gt-clean gt-run gt-run-reversed gt-run-permuted gt-log gt-log-reversed gt-log-permuted gt-summary \
        lint format clean reset

# Config
BASE         = infra/docker-compose.yml
COMPOSE_DEV  = docker compose --env-file infra/.env -f $(BASE) -f infra/docker-compose.dev.yml
COMPOSE_PROD = docker compose --env-file infra/.env -f $(BASE) -f infra/docker-compose.prod.yml
UV           = uv

# Ground truth corpus
GT_JUDGES   = ollama/qwen3:1.7b ollama/gemma3:4b ollama/phi4-mini ollama/mistral:7b
GT_CRITERIA = transparency data_privacy non_manipulation human_oversight prompt_injection
GT_LOG_ORIG = /tmp/gt_run_original.log
GT_LOG_REV  = /tmp/gt_run_reversed.log
GT_LOG_PERM = /tmp/gt_run_permuted.log

# Help
help:
	@echo ""
	@echo "  ── Quickstart ───────────────────────────────────"
	@echo "  make dev                   Start all services (hot reload)"
	@echo "  make pull-models           Pull all Ollama models"
	@echo "  make down                  Stop all services"
	@echo ""
	@echo "  ── Build ────────────────────────────────────────"
	@echo "  make build                 Build microservice images"
	@echo "  make rebuild               Build without cache + recreate all"
	@echo "  make rebuild s=evaluation  Rebuild a single service"
	@echo "  make prod                  Start built images + nginx front"
	@echo ""
	@echo "  ── Logs & status ────────────────────────────────"
	@echo "  make logs                  Follow logs (all services)"
	@echo "  make logs s=evaluation     Follow logs (one service)"
	@echo "  make ps                    Container status"
	@echo ""
	@echo "  ── Redis ────────────────────────────────────────"
	@echo "  make flush-redis           Flush entire Redis DB (⚠ all data)"
	@echo "  make flush-judge           Delete judge config only"
	@echo "  make flush-scores          Delete score matrix + eval results"
	@echo ""
	@echo "  ── Benchmark ────────────────────────────────────"
	@echo "  make benchmark             Full pipeline: generate answers + evaluate"
	@echo "  make benchmark TIMEOUT=600 Custom timeout per call"
	@echo ""
	@echo "  ── Ground truth corpus ──────────────────────────"
	@echo "  make gt-seed               DROP+CREATE tables + insert 49 cases"
	@echo "  make gt-run                Run all cases, original question order"
	@echo "  make gt-run-reversed       Run all cases, reversed question order"
	@echo "  make gt-run-permuted       Run all cases, permuted order (q2→q4→q1→q3)"
	@echo "  make gt-log                Stream log (original order)"
	@echo "  make gt-log-reversed       Stream log (reversed order)"
	@echo "  make gt-log-permuted       Stream log (permuted order)"
	@echo "  make gt-summary            Print SUMMARY block from original log"
	@echo ""
	@echo "  ── Quality ──────────────────────────────────────"
	@echo "  make lint                  Ruff + Prettier check"
	@echo "  make format                Ruff + Prettier autofix"
	@echo ""
	@echo "  ── Cleanup ──────────────────────────────────────"
	@echo "  make clean                 Remove volumes + built images"
	@echo "  make reset                 Full reset (clean + dev)"
	@echo ""

# Environments
dev:
	@cp -n infra/.env.example infra/.env 2>/dev/null && echo "Created .env from .env.example" || true
	$(COMPOSE_DEV) up -d
	@echo ""
	@echo "  Dev stack running with hot reload."
	@echo "  Edit any file in back/ — uvicorn reloads automatically."
	@echo "  Frontend: cd front && pnpm dev"
	@echo ""

prod:
	@cp -n infra/.env.example infra/.env 2>/dev/null && echo "Created .env from .env.example" || true
	$(COMPOSE_PROD) up -d --build
	@echo ""
	@echo "  Production stack running."
	@echo "  Frontend: http://localhost:5173"
	@echo ""

down:
	$(COMPOSE_DEV) down 2>/dev/null || $(COMPOSE_PROD) down

# Build
build:
	$(COMPOSE_PROD) build llm-gateway observability evaluation front

rebuild:
ifdef s
	$(COMPOSE_PROD) build --no-cache $(s)
	$(COMPOSE_PROD) up -d --force-recreate $(s)
else
	$(COMPOSE_PROD) build --no-cache llm-gateway observability evaluation front
	$(COMPOSE_PROD) up -d --force-recreate llm-gateway observability evaluation front
endif

# Logs and status
logs:
ifdef s
	$(COMPOSE_DEV) logs -f $(s)
else
	$(COMPOSE_DEV) logs -f
endif

ps:
	$(COMPOSE_DEV) ps

# Models
pull-models:
	$(COMPOSE_DEV) exec ollama ollama pull gemma3:4b
	$(COMPOSE_DEV) exec ollama ollama pull mistral:7b
	$(COMPOSE_DEV) exec ollama ollama pull phi4-mini
	$(COMPOSE_DEV) exec ollama ollama pull qwen3:1.7b

# Redis
flush-redis:
	@echo "⚠  Flushing entire Redis DB..."
	$(COMPOSE_DEV) exec redis redis-cli flushdb
	@echo "Done."

flush-judge:
	$(COMPOSE_DEV) exec redis redis-cli del config:judge
	@echo "Judge config deleted — defaults will reload on next request."

flush-scores:
	@$(COMPOSE_DEV) exec redis redis-cli --scan --pattern "eval:scores:*" | \
		xargs -r sh -c 'docker exec redis redis-cli del "$$@"' _
	@$(COMPOSE_DEV) exec redis redis-cli --scan --pattern "eval:result:*" | \
		xargs -r sh -c 'docker exec redis redis-cli del "$$@"' _
	@echo "Score matrix and eval results cleared."

# Benchmark
TIMEOUT ?= 120

benchmark:
	python scripts/run_full_benchmark.py --timeout $(TIMEOUT)

benchmark-generate:
	python scripts/run_full_benchmark.py --only-generate --timeout $(TIMEOUT)

benchmark-evaluate:
	python scripts/run_full_benchmark.py --only-evaluate --timeout $(TIMEOUT)

# Ground truth corpus
gt-seed:
	MSYS_NO_PATHCONV=1 docker exec evaluation python /app/scripts/groundtruth.py seed

gt-status:
	@MSYS_NO_PATHCONV=1 docker exec evaluation python -c \
	  "import glob; pids=[p.split('/')[2] for p in glob.glob('/proc/[0-9]*/cmdline') if b'\x00/app/scripts/groundtruth' in open(p,'rb').read()]; print(f'{len(pids)} active run(s): {pids}') if pids else print('No active run.')"

gt-kill:
	@MSYS_NO_PATHCONV=1 docker exec evaluation python -c \
	  "import os,glob,signal; pids=[int(p.split('/')[2]) for p in glob.glob('/proc/[0-9]*/cmdline') if b'\x00/app/scripts/groundtruth' in open(p,'rb').read()]; [os.kill(p,signal.SIGKILL) for p in pids]; print(f'Killed {len(pids)} process(es).')" || true

gt-clean: gt-kill
	@MSYS_NO_PATHCONV=1 docker exec evaluation sh -c "rm -f $(GT_LOG_ORIG) $(GT_LOG_REV)"
	@echo "Logs cleared."

gt-run: gt-clean
	@MSYS_NO_PATHCONV=1 docker exec -d evaluation sh -c \
	  "PYTHONUNBUFFERED=1 python -u /app/scripts/groundtruth.py run \
	   --criterion $(GT_CRITERIA) --judges $(GT_JUDGES) \
	   --order original > $(GT_LOG_ORIG) 2>&1"
	@echo "Original run started → use make gt-log to follow."

gt-run-reversed: gt-clean
	@MSYS_NO_PATHCONV=1 docker exec -d evaluation sh -c \
	  "PYTHONUNBUFFERED=1 python -u /app/scripts/groundtruth.py run \
	   --criterion $(GT_CRITERIA) --judges $(GT_JUDGES) \
	   --order reversed > $(GT_LOG_REV) 2>&1"
	@echo "Reversed run started → use make gt-log-reversed to follow."

gt-log:
	@MSYS_NO_PATHCONV=1 docker exec evaluation tail -f $(GT_LOG_ORIG)

gt-log-reversed:
	@MSYS_NO_PATHCONV=1 docker exec evaluation tail -f $(GT_LOG_REV)

gt-run-permuted: gt-clean
	@MSYS_NO_PATHCONV=1 docker exec -d evaluation sh -c \
	  "PYTHONUNBUFFERED=1 python -u /app/scripts/groundtruth.py run \
	   --criterion $(GT_CRITERIA) --judges $(GT_JUDGES) \
	   --order permuted > $(GT_LOG_PERM) 2>&1"
	@echo "Permuted run started (q2→q4→q1→q3) → use make gt-log-permuted to follow."

gt-log-permuted:
	@MSYS_NO_PATHCONV=1 docker exec evaluation tail -f $(GT_LOG_PERM)

gt-summary:
	@MSYS_NO_PATHCONV=1 docker exec evaluation sh -c \
	  "awk '/^={10}/,0' $(GT_LOG_ORIG)"

# Quality
lint:
	$(UV) tool run --native-tls ruff check back/
	cd front && npm run lint

format:
	$(UV) tool run --native-tls ruff check --fix back/
	$(UV) tool run --native-tls ruff format back/
	cd front && npm run format

# Cleanup
clean:
	$(COMPOSE_DEV) down -v --rmi local 2>/dev/null || true
	$(COMPOSE_PROD) down -v --rmi local 2>/dev/null || true

reset: clean dev
