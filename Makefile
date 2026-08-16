.PHONY: test test-unit test-integration test-evals run-api run-web run-runner clean

test: test-unit test-integration

test-unit:
	PYTHONPATH=. pytest tests/unit/ -v

test-integration:
	PYTHONPATH=. pytest tests/integration/ -v

test-evals:
	PYTHONPATH=. python tests/agent_evals/benchmarks.py

run-api:
	python3 -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload

run-web:
	cd apps/web && npm run dev

run-runner:
	cd services/runner && npm run dev

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
