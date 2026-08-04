.PHONY: install lint fmt test docker-build docker-run run

install:
	pip install -e ".[dev]"

lint:
	ruff check .
	ruff format --check .

fmt:
	ruff format .

test:
	pytest -q

run:
	secops-dispatcher

docker-build:
	docker build -t secops-dispatcher:local .

docker-run:
	docker run --rm -p 8080:8080 --env-file .env secops-dispatcher:local
