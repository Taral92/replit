import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app


@pytest.mark.asyncio
async def test_api_files_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Save a new file
        save_res = await ac.post("/files/save", json={
            "path": "test_src/hello.py",
            "content": "print('hello from api test')\n"
        })
        assert save_res.status_code == 200
        assert save_res.json()["success"] is True

        # 2. List files
        list_res = await ac.get("/files")
        assert list_res.status_code == 200
        tree = list_res.json()
        assert any(item["name"] == "test_src" or "hello.py" in str(item) for item in tree)

        # 3. Read file content
        content_res = await ac.get("/files/content", params={"path": "test_src/hello.py"})
        assert content_res.status_code == 200
        assert "hello from api test" in content_res.text

        # 4. Attempt path traversal on content endpoint
        traversal_res = await ac.get("/files/content", params={"path": "../../etc/passwd"})
        assert traversal_res.status_code in (400, 404)
