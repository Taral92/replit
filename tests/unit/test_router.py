import pytest
from services.agent.router import ModelRouter
from packages.config import settings


def test_router_manual_selection():
    model, reason = ModelRouter.route("build an app", requested_model="gpt-4o-mini")
    assert model == "gpt-4o-mini"
    assert "Manual Selection" in reason

    model, reason = ModelRouter.route("build an app", requested_model="o3-mini")
    assert model == "o3-mini"
    assert "Manual Selection" in reason


def test_router_auto_greetings():
    greetings = ["hi", "hello there", "hey", "yo", "good morning"]
    for g in greetings:
        model, reason = ModelRouter.route(g, requested_model="auto")
        assert model == settings.FAST_AGENT_MODEL
        assert "Fast Model" in reason


def test_router_auto_simple_queries():
    queries = [
        "what files are in this project?",
        "list files",
        "show directory structure",
        "how do i run this project?",
    ]
    for q in queries:
        model, reason = ModelRouter.route(q, requested_model="auto")
        assert model == settings.FAST_AGENT_MODEL
        assert "Fast Model" in reason


def test_router_auto_error_debugging():
    error_prompts = [
        "TypeError: Cannot read properties of undefined (reading 'map')",
        "Build failed with exit code 1 in page.tsx",
        "Traceback (most recent call last): File main.py",
    ]
    for ep in error_prompts:
        model, reason = ModelRouter.route(ep, requested_model="auto")
        assert model in ("gpt-4o", "o3-mini")
        assert "High-Precision" in reason or "Deep Reasoning" in reason
