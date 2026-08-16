import asyncio
import tempfile
import time
from pathlib import Path
from typing import Dict, List
from services.agent import AgentRuntime, LocalSandbox, ToolGateway, ProjectVerifier


class AgentBenchmark:
    """
    Deterministic Agent Evaluation Harness.
    Runs standardized real-world coding tasks and records pass/fail, latency, and duration.
    """

    TASKS = [
        {
            "id": "task_1_python_calc",
            "name": "Create a Python Calculator module with tests",
            "prompt": "Create a calculator.py file with add, subtract, multiply, and divide functions. Then create a test_calc.py with assertions verifying all 4 functions.",
            "verification_file": "test_calc.py",
        },
        {
            "id": "task_2_fix_bug",
            "name": "Fix failing buggy function",
            "setup": {
                "math_utils.py": "def is_prime(n):\n    if n <= 1:\n        return True # BUG\n    for i in range(2, int(n**0.5) + 1):\n        if n % i == 0:\n            return False\n    return True\n",
                "test_math.py": "from math_utils import is_prime\nassert is_prime(1) == False, '1 is not prime'\nassert is_prime(2) == True\nassert is_prime(4) == False\nprint('Tests passed')\n",
            },
            "prompt": "Run python test_math.py, observe the failure in math_utils.py, fix the bug in math_utils.py, and verify test_math.py passes.",
            "verification_file": "test_math.py",
        },
    ]

    @classmethod
    async def run_benchmark(cls, task_id: str) -> Dict:
        task = next((t for t in cls.TASKS if t["id"] == task_id), None)
        if not task:
            raise ValueError(f"Unknown task: {task_id}")

        with tempfile.TemporaryDirectory() as tmp_dir:
            sandbox = LocalSandbox(Path(tmp_dir))
            gateway = ToolGateway(sandbox)
            runtime = AgentRuntime(gateway)

            # Setup initial state if present
            if "setup" in task:
                for path, content in task["setup"].items():
                    await sandbox.write_file(path, content)

            start_time = time.time()
            events = []
            async for ev in runtime.run_stream(task["prompt"], session_id=f"eval-{task_id}"):
                events.append(ev)

            duration = time.time() - start_time

            # Verify outcome
            verify_file = task.get("verification_file")
            passed = False
            if verify_file:
                res = await sandbox.execute(f"python3 {verify_file}")
                passed = res.success

            return {
                "task_id": task_id,
                "name": task["name"],
                "passed": passed,
                "duration_seconds": round(duration, 2),
                "events_count": len(events),
            }


if __name__ == "__main__":
    async def main():
        print("Running Agent Benchmark Suite...")
        for task in AgentBenchmark.TASKS:
            res = await AgentBenchmark.run_benchmark(task["id"])
            status = "✅ PASS" if res["passed"] else "❌ FAIL"
            print(f"{status} [{res['task_id']}] {res['name']} ({res['duration_seconds']}s)")

    asyncio.run(main())
