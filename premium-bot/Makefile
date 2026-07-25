.PHONY: up down logs migrate seed test lint format admin-build zip

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

migrate:
	docker compose run --rm api alembic upgrade head

seed:
	docker compose run --rm api python -m database.seed

test:
	pytest -q

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

admin-build:
	cd admin && npm ci && npm run build

zip:
	cd .. && zip -qrFS premium-bot.zip premium-bot \
		-x 'premium-bot/.venv/*' 'premium-bot/admin/node_modules/*' \
		'premium-bot/admin/dist/*' 'premium-bot/admin/*.tsbuildinfo' \
		'premium-bot/.mypy_cache/*' 'premium-bot/.pytest_cache/*' \
		'premium-bot/.ruff_cache/*' 'premium-bot/*.egg-info/*' \
		'premium-bot/**/__pycache__/*' 'premium-bot/**/*.pyc'
