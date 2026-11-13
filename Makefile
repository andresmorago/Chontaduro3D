.DEFAULT_GOAL := help
.PHONY: help up up-tunnel down logs ps build restart shell db-shell migrate makemigration downgrade seed admin demo bootstrap test lint typecheck nuke \
	prod-build prod-up prod-up-tunnel prod-down prod-logs prod-ps prod-restart prod-shell prod-db-shell prod-admin worker-publicar

PROD := docker compose -p misimpresiones-prod -f docker-compose.prod.yml
# Las pruebas llevan su propio proyecto: nunca tocan la base de desarrollo ni la de producción.
TEST := docker compose -p misimpresiones-test --profile test

help: ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

up: ## Levanta todo (acceso local: web :3100, API :8100)
	docker compose up -d

up-tunnel: ## Levanta todo más el túnel público
	docker compose --profile tunnel up -d

down: ## Detiene los servicios (conserva los datos)
	docker compose --profile tunnel down

logs: ## Sigue los logs (make logs s=backend)
	docker compose logs -f $(s)

ps: ## Estado de los servicios
	docker compose ps

build: ## Reconstruye las imágenes
	docker compose build

restart: ## Reinicia un servicio (make restart s=backend)
	docker compose restart $(s)

shell: ## Shell dentro del backend
	docker compose exec backend bash

db-shell: ## psql dentro de la base
	docker compose exec db psql -U $${POSTGRES_USER:-impresiones} -d $${POSTGRES_DB:-misimpresiones}

migrate: ## Aplica las migraciones pendientes (idempotente)
	docker compose exec backend python -m app.migrar

makemigration: ## Genera una migración (make makemigration m="mensaje")
	docker compose exec backend alembic revision --autogenerate -m "$(m)"

downgrade: ## Revierte la última migración
	docker compose exec backend alembic downgrade -1

seed: ## Siembra lo mínimo (idempotente)
	docker compose exec backend python -m app.seeds.run

admin: ## Crea o actualiza el usuario administrador
	docker compose exec backend python -m app.seeds.create_admin

demo: ## Carga artículos de EJEMPLO (rotulados como tales)
	docker compose exec backend python -m app.seeds.demo

bootstrap: up migrate seed admin ## Levanta, migra, siembra y crea el admin

test: ## Corre las pruebas del backend en una base desechable
	$(TEST) run --rm tests; r=$$?; $(TEST) down -v >/dev/null 2>&1; exit $$r

lint: ## Formatea y revisa el backend
	docker compose exec backend ruff format app tests
	docker compose exec backend ruff check --fix app tests

typecheck: ## Tipos y lint del frontend
	docker compose exec frontend npm run typecheck
	docker compose exec frontend npm run lint

nuke: ## Borra TODO, incluidos los datos de desarrollo
	docker compose --profile tunnel down -v

# --- Producción ---------------------------------------------------------------
prod-build: ## Reconstruye las imágenes de producción
	$(PROD) build

prod-up: ## Levanta producción (sin túnel)
	$(PROD) up -d

prod-up-tunnel: ## Levanta producción con túnel público
	$(PROD) --profile tunnel up -d

prod-down: ## Detiene producción (conserva los datos)
	$(PROD) --profile tunnel down

prod-logs: ## Logs de producción (make prod-logs s=backend)
	$(PROD) logs -f $(s)

prod-ps: ## Estado de producción
	$(PROD) ps

prod-restart: ## Reinicia un servicio de producción
	$(PROD) restart $(s)

prod-shell: ## Shell dentro del backend de producción
	$(PROD) exec backend bash

prod-db-shell: ## psql en la base de producción
	$(PROD) exec db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}

prod-admin: ## Crea o actualiza el admin en producción
	$(PROD) exec backend python -m app.seeds.create_admin

worker-publicar: ## Sube el Worker de workers.dev apuntando al túnel actual
	$(PROD) --profile tunnel logs cloudflared 2>&1 | python3 cloudflare/urlsync/urlsync.py --una-vez
