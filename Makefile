.DEFAULT_GOAL := help
.PHONY: help up up-tunnel down logs ps build restart shell db-shell migrate makemigration downgrade seed admin demo bootstrap test lint typecheck nuke \
	prod-build prod-up prod-up-tunnel prod-down prod-logs prod-ps prod-restart prod-shell prod-db-shell prod-admin worker-publicar e2e iphone desbordes impresora-up impresora-logs prod-impresora-logs bambu-login bambu-nube-prueba

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
	docker compose --profile tunnel --profile impresora down

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

worker-publicar: ## Sube una vez el Worker de workers.dev apuntando al túnel actual (producción)
	$(PROD) --profile tunnel run --rm urlsync python /cloudflare/urlsync/urlsync.py --una-vez

# --- Impresora 3D (Bambu Lab A1) ----------------------------------------------
impresora-up: ## Desarrollo: levanta el servicio de la impresora (necesita BAMBU_* en .env)
	docker compose --profile impresora up -d impresora

impresora-logs: ## Desarrollo: logs del servicio de la impresora
	docker compose --profile impresora logs -f --tail 50 impresora

prod-impresora-logs: ## Producción: logs del servicio de la impresora
	$(PROD) logs -f --tail 50 impresora

bambu-login: ## Inicia sesión en Bambu Cloud y guarda SOLO el token en data/nube (make bambu-login ARGS=--pegar si falla)
	@mkdir -p data/nube && chmod 700 data/nube
	python3 scripts/bambu_login.py $(ARGS)

bambu-nube-prueba: ## Producción: diagnóstico del historial de Bambu Cloud (forma de los datos, sin secretos)
	$(PROD) exec -T impresora python -m app.impresora.nube_prueba

# --- Pruebas de punta a punta -------------------------------------------------
# Solo contra el stack de DESARROLLO (make up). Los límites anti-abuso también aplican aquí
# (5 pedidos por hora y 10 ingresos fallidos por 15 min desde un mismo origen): conviene no
# correrlo más de unas 5 veces por hora.
e2e: ## Recorrido completo con navegador real (Playwright); capturas en e2e/out
	@docker compose exec -T backend python -m app.seeds.trabajos_ejemplo
	@test -f e2e/grande.png || docker compose exec -T backend python -c "import os, sys; from PIL import Image; w, h = 3000, 2200; Image.frombytes('RGB', (w, h), os.urandom(w * h * 3)).save(sys.stdout.buffer, 'PNG')" > e2e/grande.png
	@set -a && . ./.env && set +a && docker run --rm --network misimpresiones_default -v "$$PWD/e2e:/work" -w /work -e ADMIN_EMAIL -e ADMIN_PASSWORD mcr.microsoft.com/playwright:v1.56.1-noble bash -c "npm i --no-audit --no-fund playwright@1.56.1 >/dev/null 2>&1 && node recorrido.mjs"

desbordes: ## Detecta texto que se sale de su caja (sitio público y panel, 9 anchos); necesita make up + make impresora-up
	@set -a && . ./.env && set +a && docker run --rm --network misimpresiones_default -v "$$PWD/e2e:/work" -w /work -e ADMIN_EMAIL -e ADMIN_PASSWORD mcr.microsoft.com/playwright:v1.56.1-noble bash -c "npm i --no-audit --no-fund playwright@1.56.1 >/dev/null 2>&1 && node desbordes.mjs"

iphone: ## Prueba en WebKit (motor de Safari) con perfiles de iPhone SE, 13 y 15 Pro Max
	@set -a && . ./.env && set +a && docker run --rm --network misimpresiones_default -v "$$PWD/e2e:/work" -w /work -e ADMIN_EMAIL -e ADMIN_PASSWORD mcr.microsoft.com/playwright:v1.56.1-noble bash -c "npm i --no-audit --no-fund playwright@1.56.1 >/dev/null 2>&1 && node iphone.mjs"
