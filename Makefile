.PHONY: install lint test audit build local deploy-dev deploy-prod seed smoke loadtest scale-demo fault-demo

install:
	pip install -r requirements-dev.txt

lint:
	ruff check .

test:
	pytest -q

audit:
	pip-audit -r requirements-dev.txt

local:
	python scripts/local_server.py

build:
	sam build -t infra/template.yaml

deploy-dev: build
	sam deploy --config-file infra/samconfig.toml --config-env dev

deploy-prod: build
	sam deploy --config-file infra/samconfig.toml --config-env prod

seed:
	python scripts/seed_data.py --stack hawkerflow-dev

smoke:
	python scripts/smoke.py --stack hawkerflow-dev

loadtest:
	k6 run loadtest/order_flow.js

# Independent-scalability evidence: drive ONE service and watch only it scale
scale-demo:
	k6 run loadtest/order_flow.js -e SERVICE=catalog -e RATE=100 -e DURATION=5m

# Fault-isolation evidence: break one service, prove the rest keeps working
fault-demo:
	python scripts/fault_isolation_demo.py --stack hawkerflow-dev
