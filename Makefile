PYTHON ?= python

.PHONY: install lint test audit build deploy-dev deploy-prod seed smoke loadtest

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

lint:
	ruff check .

test:
	pytest -q

audit:
	pip-audit -r requirements-dev.txt

build:
	sam build -t infra/template.yaml

deploy-dev: build
	sam deploy --config-file infra/samconfig.toml --config-env dev

deploy-prod: build
	sam deploy --config-file infra/samconfig.toml --config-env prod

seed:
	$(PYTHON) scripts/seed_data.py --stack hawkerflow-dev

smoke:
	$(PYTHON) scripts/smoke.py --stack hawkerflow-dev

loadtest:
	k6 run loadtest/order_flow.js
