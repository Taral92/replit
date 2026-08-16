import asyncio
import os
import sys

from pathlib import Path
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from apps.api.main import get_or_create_session

async def main():
    ctx = get_or_create_session(session_id="eval_session", workspace_id="todo-app")
    prompt = "build a simple todo app in Next.js with minimal design"
    
    print(f"Starting agent run for prompt: {prompt}")
    
    async def on_event(event):
        # We can just let the stream yield it or use callback
        pass

    async for event in ctx.agent.run_stream(
        prompt=prompt,
        session_id="eval_session",
        requested_model="auto",
        event_callback=on_event
    ):
        event_type = event.get("type")
        if event_type == "turn_completed":
            print("\n\n--- REPORT ---")
            print(f"Metrics: {event.get('metrics')}")
            print(f"Duration: {event.get('duration_ms')} ms")
        elif event_type == "tool_completed":
            print(f"Tool {event.get('tool')} finished: {event.get('status')}")
        elif event_type == "step":
            print(f"Step: {event.get('tool')} - {event.get('action')}")
        elif event_type == "status":
            print(f"Status: {event.get('status')}")
        elif event_type == "message":
            print(f"Msg: {event.get('content')}")

if __name__ == "__main__":
    asyncio.run(main())
