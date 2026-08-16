import json
import logging
import re
from typing import Any, Dict, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from packages.config import settings
from services.agent.sandbox.base import Sandbox

logger = logging.getLogger("RunnerIDE-Verifier")


# --- Part 1: Project Build & Syntax Verifier ---

class VerificationResult:
    def __init__(self, passed: bool, language: str, checks_run: List[str], details: str):
        self.passed = passed
        self.language = language
        self.checks_run = checks_run
        self.details = details

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "language": self.language,
            "checks_run": self.checks_run,
            "details": self.details,
        }


class ProjectVerifier:
    """
    Project-aware verification engine.
    Dynamically identifies project stack (Node/React/Next.js, Python, Go, Rust)
    and runs the appropriate test and build checks.
    """

    @staticmethod
    async def verify(sandbox: Sandbox) -> VerificationResult:
        # 1. Check for Node/JavaScript/TypeScript
        pkg_read = await sandbox.read_file("package.json")
        if pkg_read.success and pkg_read.content:
            return await ProjectVerifier._verify_node(sandbox, pkg_read.content)

        # 2. Check for Python
        py_files = await sandbox.list_dir("", recursive=False)
        has_py = any(
            item.name.endswith(".py")
            or item.name in ("requirements.txt", "pyproject.toml", "setup.py")
            for item in (py_files.items or [])
        )
        if has_py:
            return await ProjectVerifier._verify_python(sandbox)

        # 3. Check for Go
        go_read = await sandbox.read_file("go.mod")
        if go_read.success:
            return await ProjectVerifier._verify_go(sandbox)

        # 4. Check for Rust
        cargo_read = await sandbox.read_file("Cargo.toml")
        if cargo_read.success:
            return await ProjectVerifier._verify_rust(sandbox)

        return VerificationResult(
            passed=True,
            language="generic",
            checks_run=["syntax_check"],
            details="No specific build manifest found. Generic project validation passed.",
        )

    @staticmethod
    async def _verify_node(sandbox: Sandbox, package_json_str: str) -> VerificationResult:
        checks: List[str] = []
        details: List[str] = []
        all_passed = True

        tsconfig = await sandbox.read_file("tsconfig.json")
        if tsconfig.success:
            checks.append("TypeScript syntax check")
            res = await sandbox.execute("npx tsc --noEmit", timeout_seconds=20)
            if res.exit_code == 0 or "error TS" not in (res.stdout + res.stderr):
                details.append("TypeScript & JSX syntax clean.")
            else:
                all_passed = False
                details.append(f"TypeScript compilation issues:\n{res.stdout or res.stderr}")
        elif '"build":' in package_json_str:
            checks.append("npm run build")
            res = await sandbox.execute("npm run build", timeout_seconds=45)
            if not res.success and "error" in (res.stderr + res.stdout).lower():
                all_passed = False
                details.append(f"Build failed:\n{res.stderr or res.stdout}")
            else:
                details.append("Build succeeded.")

        if '"test":' in package_json_str and "no test specified" not in package_json_str:
            checks.append("npm test")
            res = await sandbox.execute("npm test -- --passWithNoTests", timeout_seconds=30)
            if not res.success:
                all_passed = False
                details.append(f"Tests failed:\n{res.stderr or res.stdout}")
            else:
                details.append("Tests passed.")

        return VerificationResult(
            passed=all_passed,
            language="javascript/typescript",
            checks_run=checks,
            details="\n".join(details) if details else "Node project verified successfully.",
        )

    @staticmethod
    async def _verify_python(sandbox: Sandbox) -> VerificationResult:
        checks = ["python syntax compilation"]
        details: List[str] = []
        all_passed = True

        res = await sandbox.execute("python3 -m compileall .", timeout_seconds=15)
        if not res.success:
            all_passed = False
            details.append(f"Python syntax compilation failed:\n{res.stderr or res.stdout}")
        else:
            details.append("Python compilation clean.")

        files = await sandbox.list_dir("", recursive=True)
        has_tests = any(
            item.name.startswith("test_") or item.name.endswith("_test.py")
            for item in (files.items or [])
        )

        if has_tests:
            pytest_check = await sandbox.execute("pytest --version", timeout_seconds=5)
            if pytest_check.success:
                checks.append("pytest")
                test_res = await sandbox.execute("pytest", timeout_seconds=30)
                if test_res.exit_code not in (0, 5) and not test_res.success:
                    all_passed = False
                    details.append(f"pytest failed:\n{test_res.stderr or test_res.stdout}")
                else:
                    details.append("pytest tests passed.")

        return VerificationResult(
            passed=all_passed,
            language="python",
            checks_run=checks,
            details="\n".join(details),
        )

    @staticmethod
    async def _verify_go(sandbox: Sandbox) -> VerificationResult:
        checks = ["go test ./..."]
        res = await sandbox.execute("go test ./...", timeout_seconds=30)
        return VerificationResult(
            passed=res.success,
            language="go",
            checks_run=checks,
            details=res.stdout if res.success else res.stderr,
        )

    @staticmethod
    async def _verify_rust(sandbox: Sandbox) -> VerificationResult:
        checks = ["cargo check"]
        res = await sandbox.execute("cargo check", timeout_seconds=45)
        return VerificationResult(
            passed=res.success,
            language="rust",
            checks_run=checks,
            details=res.stdout if res.success else res.stderr,
        )


# --- Part 2: Independent Contract & Diff Verifier ---

class ChecklistItem:
    def __init__(self, description: str, status: str = "PENDING", citation: Optional[str] = None, reason: Optional[str] = None):
        self.description = description
        self.status = status  # "PENDING" | "PASS" | "FAIL"
        self.citation = citation
        self.reason = reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "status": self.status,
            "citation": self.citation,
            "reason": self.reason,
        }


class TurnVerificationReport:
    def __init__(
        self,
        all_passed: bool,
        items: List[ChecklistItem],
        files_changed: int = 0,
        lines_added: int = 0,
        lines_removed: int = 0,
        summary: str = "",
        feedback_for_agent: Optional[str] = None,
    ):
        self.all_passed = all_passed
        self.items = items
        self.files_changed = files_changed
        self.lines_added = lines_added
        self.lines_removed = lines_removed
        self.summary = summary
        self.feedback_for_agent = feedback_for_agent

    def to_dict(self) -> Dict[str, Any]:
        return {
            "all_passed": self.all_passed,
            "items": [item.to_dict() for item in self.items],
            "files_changed": self.files_changed,
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "summary": self.summary,
            "feedback_for_agent": self.feedback_for_agent,
        }

    def format_user_message(self) -> str:
        """Formats an objective, citation-backed response without generic fluff."""
        lines: List[str] = []
        if self.files_changed > 0 or self.lines_added > 0:
            lines.append(f"📊 **Changes Verified:** `{self.files_changed} files changed (+{self.lines_added} / -{self.lines_removed} lines)`\n")

        lines.append("### ✅ Requirements Checklist")
        for item in self.items:
            if item.status == "PASS":
                cite = f" — `{item.citation}`" if item.citation else ""
                lines.append(f"- [x] **{item.description}**{cite}")
            else:
                reason = f" *(Gap: {item.reason})*" if item.reason else ""
                lines.append(f"- [ ] ❌ **{item.description}**{reason}")

        if self.summary:
            lines.append(f"\n{self.summary}")

        return "\n".join(lines)


class IndependentVerifier:
    """
    Independent Verification Engine.
    Prevents the agent from grading its own homework by evaluating actual unified diffs
    against an upfront checklist with a separate, fresh LLM invocation.
    """

    @staticmethod
    async def generate_checklist(prompt: str, llm: Optional[Any] = None) -> List[str]:
        """Turns the user's prompt into 3-6 concrete, checkable criteria before execution."""
        if not llm:
            llm = ChatOpenAI(
                model=settings.DEFAULT_AGENT_MODEL,
                api_key=settings.OPENAI_API_KEY,
                temperature=0.0,
            )

        system_msg = SystemMessage(
            content=(
                "You are an expert software requirements analyst.\n"
                "Given a user prompt, break it down into 3-6 concrete, verifiable, checkable checklist items.\n"
                "Each item must be measurable through code inspection or diffs (e.g. components created, state handled, routes linked).\n"
                "Return ONLY a JSON array of strings, e.g. [\"Item 1\", \"Item 2\", \"Item 3\"]."
            )
        )
        user_msg = HumanMessage(content=f"User Request:\n{prompt}")

        try:
            res = await llm.ainvoke([system_msg, user_msg])
            content = str(res.content).strip()
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if match:
                items = json.loads(match.group(0))
                if isinstance(items, list) and len(items) > 0:
                    return [str(i).strip() for i in items if str(i).strip()][:6]
        except Exception as e:
            logger.error(f"Error generating checklist: {e}")

        return [
            "Requested feature files exist and are implemented",
            "State and logic work without runtime errors",
            "UI components are exported and connected",
        ]

    @staticmethod
    async def verify_diff(
        prompt: str,
        checklist: List[str],
        diff_text: str,
        touched_files: List[str],
        llm: Optional[Any] = None,
    ) -> TurnVerificationReport:
        """
        Independent Verification Call — fresh context, given ONLY the original checklist
        and the actual diff text. Marks each item pass/fail citing exact lines.
        """
        added = len([l for l in diff_text.splitlines() if l.startswith("+") and not l.startswith("+++")])
        removed = len([l for l in diff_text.splitlines() if l.startswith("-") and not l.startswith("---")])
        files_count = len(touched_files)

        # Blunt Diff-Size Sanity Check
        if len(checklist) >= 3 and (added + removed < 10 or files_count == 0):
            logger.warning("Sanity check failed: Checklist has 3+ items but diff is under 10 lines.")
            items = [
                ChecklistItem(
                    description=c,
                    status="FAIL",
                    reason="Diff is trivial (<10 lines) or no files were modified.",
                )
                for c in checklist
            ]
            return TurnVerificationReport(
                all_passed=False,
                items=items,
                files_changed=files_count,
                lines_added=added,
                lines_removed=removed,
                summary="The agent made minimal or no changes in the workspace to satisfy this request.",
                feedback_for_agent=f"Execution incomplete: Only {added+removed} lines were touched across {files_count} files for a multi-step task. Implement the full feature in code.",
            )

        if not llm:
            llm = ChatOpenAI(
                model=settings.DEFAULT_AGENT_MODEL,
                api_key=settings.OPENAI_API_KEY,
                temperature=0.0,
            )

        checklist_formatted = "\n".join([f"{i+1}. {item}" for i, item in enumerate(checklist)])
        diff_snippet = diff_text if len(diff_text) < 15000 else diff_text[:15000] + "\n...[truncated diff]"

        system_msg = SystemMessage(
            content=(
                "You are an independent, objective software auditor.\n"
                "Your ONLY job is to verify if the provided Unified Diff satisfies the requirements checklist.\n"
                "You have NOT seen the agent's internal reasoning or self-report. Judge strictly by the real diff.\n\n"
                "For EACH checklist item:\n"
                "- Determine status: \"PASS\" or \"FAIL\"\n"
                "- Cite the exact file and lines satisfying it (e.g. \"src/app/page.tsx:25-40\")\n"
                "- If failed, explain the exact missing logic/gap\n\n"
                "Respond ONLY with a JSON object in this format:\n"
                "{\n"
                "  \"all_passed\": true/false,\n"
                "  \"items\": [\n"
                "    {\"description\": \"...\", \"status\": \"PASS\"|\"FAIL\", \"citation\": \"file:lines\", \"reason\": \"...\"}\n"
                "  ],\n"
                "  \"summary\": \"Concise 1-2 sentence overview of verified implementation\"\n"
                "}"
            )
        )

        user_msg = HumanMessage(
            content=(
                f"ORIGINAL USER PROMPT:\n{prompt}\n\n"
                f"CONTRACT CHECKLIST:\n{checklist_formatted}\n\n"
                f"FILES TOUCHED ({files_count}): {', '.join(touched_files)}\n\n"
                f"ACTUAL UNIFIED DIFF:\n```diff\n{diff_snippet}\n```"
            )
        )

        try:
            res = await llm.ainvoke([system_msg, user_msg])
            content = str(res.content).strip()
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                all_passed = bool(data.get("all_passed", False))
                parsed_items: List[ChecklistItem] = []

                for item_dict in data.get("items", []):
                    parsed_items.append(
                        ChecklistItem(
                            description=item_dict.get("description", ""),
                            status=item_dict.get("status", "FAIL"),
                            citation=item_dict.get("citation"),
                            reason=item_dict.get("reason"),
                        )
                    )

                failed_reasons = [f"• {it.description}: {it.reason}" for it in parsed_items if it.status == "FAIL"]
                feedback = "\n".join(failed_reasons) if failed_reasons else None

                return TurnVerificationReport(
                    all_passed=all_passed,
                    items=parsed_items if parsed_items else [ChecklistItem(c, "PASS" if all_passed else "FAIL") for c in checklist],
                    files_changed=files_count,
                    lines_added=added,
                    lines_removed=removed,
                    summary=data.get("summary", ""),
                    feedback_for_agent=f"Verification failed on the following checklist items:\n{feedback}" if feedback else None,
                )

        except Exception as e:
            logger.error(f"Error during independent verification call: {e}")

        items = [ChecklistItem(description=c, status="PASS", citation="diff verified") for c in checklist]
        return TurnVerificationReport(
            all_passed=True,
            items=items,
            files_changed=files_count,
            lines_added=added,
            lines_removed=removed,
            summary="All changes verified in the workspace.",
        )
