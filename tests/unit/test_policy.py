import tempfile
from pathlib import Path
import pytest
from services.agent.gateway.policy import PolicyEngine


def test_path_traversal_prevention():
    with tempfile.TemporaryDirectory() as tmp_dir:
        base_path = Path(tmp_dir)
        (base_path / "src").mkdir()
        (base_path / "src" / "index.js").write_text("console.log('hello');")

        # Valid relative paths
        valid, resolved, err = PolicyEngine.resolve_and_validate_path(base_path, "src/index.js")
        assert valid is True
        assert resolved == (base_path / "src" / "index.js").resolve()
        assert err is None

        # Traversal attempts
        invalid_paths = [
            "../../etc/passwd",
            "../outside.txt",
            "/etc/shadow",
            "src/../../outside.txt",
        ]

        for p in invalid_paths:
            valid, resolved, err = PolicyEngine.resolve_and_validate_path(base_path, p)
            assert valid is False, f"Expected {p} to be rejected"
            assert "traversal denied" in (err or "").lower()


def test_command_classification():
    # Safe commands
    safe_cmds = ["ls -la", "cat README.md", "git status", "npm test", "pytest"]
    for cmd in safe_cmds:
        risk, _ = PolicyEngine.classify_command(cmd)
        assert risk == "safe", f"Expected '{cmd}' to be safe, got {risk}"

    # Restricted commands
    restricted_cmds = ["npm install react", "git commit -m 'feat'", "mkdir components"]
    for cmd in restricted_cmds:
        risk, _ = PolicyEngine.classify_command(cmd)
        assert risk == "restricted", f"Expected '{cmd}' to be restricted, got {risk}"

    # Destructive commands
    destructive_cmds = ["rm -rf node_modules", "rm -r src", "git reset --hard HEAD~1", "DROP DATABASE test"]
    for cmd in destructive_cmds:
        risk, _ = PolicyEngine.classify_command(cmd)
        assert risk == "destructive", f"Expected '{cmd}' to be destructive, got {risk}"

    # Privileged commands
    privileged_cmds = ["sudo apt update", "chmod 777 script.sh", "kubectl delete pod my-pod", "docker run alpine"]
    for cmd in privileged_cmds:
        risk, _ = PolicyEngine.classify_command(cmd)
        assert risk == "privileged", f"Expected '{cmd}' to be privileged, got {risk}"


def test_human_approval_requirement():
    assert PolicyEngine.requires_human_approval("safe") is False
    assert PolicyEngine.requires_human_approval("restricted") is False
    assert PolicyEngine.requires_human_approval("destructive") is True
    assert PolicyEngine.requires_human_approval("privileged") is True
