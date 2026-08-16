import tempfile
from pathlib import Path
import pytest
from services.agent.sandbox.local import LocalSandbox


@pytest.mark.asyncio
async def test_sandbox_file_operations():
    with tempfile.TemporaryDirectory() as tmp_dir:
        sandbox = LocalSandbox(Path(tmp_dir))

        # Write file
        w_res = await sandbox.write_file("src/app.py", "print('hello world')\n")
        assert w_res.success is True
        assert w_res.added == 1

        # Read file
        r_res = await sandbox.read_file("src/app.py")
        assert r_res.success is True
        assert "hello world" in (r_res.content or "")

        # Patch file
        p_res = await sandbox.patch_file("src/app.py", "hello world", "hello runner ide")
        assert p_res.success is True
        assert p_res.diff is not None

        # Verify patch applied
        r_res2 = await sandbox.read_file("src/app.py")
        assert "hello runner ide" in (r_res2.content or "")

        # List dir
        l_res = await sandbox.list_dir("", recursive=True)
        assert l_res.success is True
        assert len(l_res.items) > 0


@pytest.mark.asyncio
async def test_search_prevents_shell_injection():
    with tempfile.TemporaryDirectory() as tmp_dir:
        sandbox = LocalSandbox(Path(tmp_dir))
        await sandbox.write_file("notes.txt", "important note about testing\n")

        # Attempt shell injection with single quote breakout
        evil_query = "note'; touch /tmp/pwned.txt; echo '"
        s_res = await sandbox.search(evil_query)
        assert s_res.success is True
        # Ensure the malicious command did not execute
        assert not Path("/tmp/pwned.txt").exists()


@pytest.mark.asyncio
async def test_command_execution_timeout():
    with tempfile.TemporaryDirectory() as tmp_dir:
        sandbox = LocalSandbox(Path(tmp_dir))

        # Normal fast command
        res = await sandbox.execute("echo 'ok'")
        assert res.success is True
        assert "ok" in res.stdout

        # Command that would hang if not timed out
        res_timeout = await sandbox.execute("sleep 10", timeout_seconds=1)
        assert res_timeout.success is False
        assert "timed out" in (res_timeout.error or "").lower()
