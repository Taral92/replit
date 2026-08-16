import asyncio
from apps.api.main import SessionContext

async def main():
    ctx = SessionContext(session_id="test_session", workspace_id="todo-app")
    print("Success")

asyncio.run(main())
