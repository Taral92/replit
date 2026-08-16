import tempfile
from pathlib import Path
import pytest
from services.agent.sandbox.local import LocalSandbox
from services.agent.verifier import ProjectVerifier


@pytest.mark.asyncio
async def test_verifier_python_project():
    with tempfile.TemporaryDirectory() as tmp_dir:
        sandbox = LocalSandbox(Path(tmp_dir))
        await sandbox.write_file("main.py", "def add(a, b):\n    return a + b\n")

        result = await ProjectVerifier.verify(sandbox)
        assert result.language == "python"
        assert result.passed is True


@pytest.mark.asyncio
async def test_verifier_python_syntax_error():
    with tempfile.TemporaryDirectory() as tmp_dir:
        sandbox = LocalSandbox(Path(tmp_dir))
        # Intentionally invalid syntax
        await sandbox.write_file("main.py", "def add(a, b)\n    return a + b\n")

        result = await ProjectVerifier.verify(sandbox)
        assert result.language == "python"
        assert result.passed is False
