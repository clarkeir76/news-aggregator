.PHONY: help install dev-install lint format test test-local test-cov clean deploy

help:
	@echo "News Aggregator - Available Commands:"
	@echo "  make install        - Install production dependencies"
	@echo "  make dev-install    - Install development dependencies"
	@echo "  make lint           - Run linting and type checking"
	@echo "  make format         - Format code with black"
	@echo "  make test           - Run unit tests (no Docker required)"
	@echo "  make test-local     - Run all tests including DynamoDB Local integration tests"
	@echo "                        (requires: docker-compose up -d dynamodb-local)"
	@echo "  make test-cov       - Run tests with coverage"
	@echo "  make clean          - Remove build artifacts and cache"
	@echo "  make deploy         - Deploy infrastructure and application"

install:
	pip install -r requirements.txt

dev-install: install
	pip install pytest pytest-cov pytest-mock black flake8 mypy

lint:
	black --check app/ tests/
	flake8 app/ tests/
	mypy app/src/ --ignore-missing-imports

format:
	black app/ tests/

test:
	pytest tests/ -v --ignore=tests/integration_test.py --ignore=tests/test_persistence_dynamo_local.py

test-local:
	pytest tests/ -v --ignore=tests/integration_test.py

test-cov:
	pytest tests/ -v --cov=app/src --cov-report=html --cov-report=term

clean:
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -delete
	find . -type d -name '.pytest_cache' -delete
	find . -type d -name '.mypy_cache' -delete
	find . -type d -name 'htmlcov' -delete
	find . -type d -name '.coverage' -delete
	rm -rf build/ dist/ *.egg-info

# Lambda packaging
lambda-build:
	mkdir -p build/
	pip install -r requirements.txt -t build/
	cp -r app build/
	cp config/feeds.yaml build/opt/config/feeds.yaml
	cd build && zip -r ../lambda_function.zip .

# Terraform
tf-init:
	cd infra/terraform && terraform init

tf-plan:
	cd infra/terraform && terraform plan

tf-apply:
	cd infra/terraform && terraform apply

tf-destroy:
	cd infra/terraform && terraform destroy

# Development
dev-run:
	python -m app.lambda_handler

# Docker for Lambda testing
docker-build:
	docker build -f Dockerfile -t news-aggregator:latest .

docker-run:
	docker run -e LOG_LEVEL=DEBUG -e ENABLE_SLACK=false -e ENABLE_SUMMARIZATION=false news-aggregator:latest
