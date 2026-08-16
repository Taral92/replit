import asyncio
import os
import shlex
import time
from pathlib import Path
from services.workspace_manager.server_manager import DevServerManager

async def main():
    workspace = Path("/Users/taralbabubhaipatel/Downloads/replit/workspaces/todo-app")
    
    mgr = DevServerManager(workspace)
    env = mgr._get_enhanced_env()
    print("PATH:", env["PATH"])
    args = shlex.split("npm run dev")
    print("ARGS:", args)
    
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(workspace),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        preexec_fn=os.setsid if hasattr(os, "setsid") else None,
    )
    print("PID:", proc.pid)
    
    start = time.time()
    while time.time() - start < 3:
        if proc.returncode is not None:
            print("EXITED:", proc.returncode)
            break
        try:
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=0.1)
            if line:
                print("OUT:", line.decode().strip())
        except asyncio.TimeoutError:
            pass
    if proc.returncode is None:
        print("Still running!")
        proc.kill()
    else:
        print("Final exit code:", proc.returncode)

asyncio.run(main())
