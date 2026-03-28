.PHONY: help dev prod down build rebuild logs ps \
        pull-models \
        flush-redis flush-judge flush-scores \
        lint test clean reset

# Config 
BASE         = infra/docker-compose.yml
COMPOSE_DEV  = docker compose --env-file infra/.env -f $(BASE) -f infra/docker-compose.dev.yml
COMPOSE_PROD = docker compose --env-file infra/.env -f $(BASE) -f infra/docker-compose.prod.yml
UV           = uv

# Help 
help:
	@echo ""
	@echo "  ── Environments ─────────────────────────────────"
	@echo "  make dev                   Start all services with hot reload"
	@echo "  make prod                  Start all services (built images + nginx front)"
	@echo "  make down                  Stop all services"
	@echo ""
	@echo "  ── Build ────────────────────────────────────────"
	@echo "  make build                 Build microservice images"
	@echo "  make rebuild               Build without cache + recreate all"
	@echo "  make rebuild s=evaluation  Rebuild a single service"
	@echo ""
	@echo "  ── Logs & status ────────────────────────────────"
	@echo "  make logs                  Follow logs (all services)"
	@echo "  make logs s=evaluation     Follow logs (one service)"
	@echo "  make ps                    Container status"
	@echo ""
	@echo "  ── Models ───────────────────────────────────────"
	@echo "  make pull-models           Pull all Ollama models"
	@echo ""
	@echo "  ── Redis ────────────────────────────────────────"
	@echo "  make flush-redis           Flush entire Redis DB (⚠ all data)"
	@echo "  make flush-judge           Delete judge config only"
	@echo "  make flush-scores          Delete score matrix + eval results"
	@echo ""
	@echo "  ── Quality ──────────────────────────────────────"
	@echo "  make lint                  Ruff lint on back/"
	@echo "  make test                  Run pytest"
	@echo ""
	@echo "  ── Cleanup ──────────────────────────────────────"
	@echo "  make clean                 Remove volumes + built images"
	@echo "  make reset                 Full reset (clean + dev)"
	@echo ""

# Environments 
# TODO: check hot reload seems broken
dev:
	@cp -n infra/.env.example infra/.env 2>/dev/null && echo "Created .env from .env.example" || true
	$(COMPOSE_DEV) up -d
	@echo ""
	@echo "  Dev stack running with hot reload."
	@echo "  Edit any file in back/ uvicorn reloads automatically."
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
	$(COMPOSE_DEV) exec ollama ollama pull gemma3:1b
	$(COMPOSE_DEV) exec ollama ollama pull llama3.2:3b
	$(COMPOSE_DEV) exec ollama ollama pull qwen2.5:1.5b
	$(COMPOSE_DEV) exec ollama ollama pull deepseek-r1:1.5b

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

# Quality
lint:
	$(UV) tool run ruff check back/

# TODO: add some tests
# test:
# 	PYTHONPATH=back/shared/src:back/llm-gateway:back/observability:back/evaluation \
# 	$(UV) run pytest back/ -v

# Cleanup
clean:
	$(COMPOSE_DEV) down -v --rmi local 2>/dev/null || true
	$(COMPOSE_PROD) down -v --rmi local 2>/dev/null || true

reset: clean dev