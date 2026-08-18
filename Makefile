.PHONY: test test-unit test-integration test-evals run-api run-web run-runner clean

test: test-unit test-integration

test-unit:
	PYTHONPATH=. pytest tests/unit/ -v

test-integration:
	PYTHONPATH=. pytest tests/integration/ -v

test-evals:
	PYTHONPATH=. python tests/agent_evals/benchmarks.py

# --reload-dir is load-bearing, not tidiness.
#
# Plain --reload watches the whole repo, which includes workspaces/ — the
# directory the agent writes user projects into. Every file the agent created
# and every npm install therefore restarted the API, which dropped the
# websocket (the client visibly reconnects) and killed the dev server, since it
# is spawned as a child of this process. That looked like "the dev server keeps
# stopping by itself" and was actually us killing it.
#
# Watch only our own source.
run-api:
	python3 -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload \
		--reload-dir apps/api --reload-dir services --reload-dir packages

run-web:
	cd apps/web && npm run dev

run-runner:
	cd services/runner && npm run dev

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
