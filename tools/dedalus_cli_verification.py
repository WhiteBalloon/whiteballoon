#!/usr/bin/env python3
"""Option A POC: use Dedalus to drive an existing WhiteBalloon CLI workflow."""
from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import signal
import subprocess
import sys
from pathlib import Path
from typing import Optional

LOG_PREFIX = "[dedalus-cli]"


def _pre_boot_interrupt(signum, frame) -> None:  # pragma: no cover - signal handler
    print(f"{LOG_PREFIX} Interrupted before startup; exiting", flush=True)
    raise SystemExit(0)


signal.signal(signal.SIGINT, _pre_boot_interrupt)

from app.env import ensure_env_loaded
from app.dedalus.logging import (
    finalize_from_response,
    finalize_logged_run,
    instrument_tools,
    start_logged_run,
)

try:  # pragma: no cover - optional dependency check
    from dedalus_labs import AsyncDedalus, DedalusRunner
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit(
        "Missing 'dedalus-labs' SDK. Run './wb setup' or 'pip install dedalus-labs' inside the venv."
    ) from exc

REPO_ROOT = Path(__file__).resolve().parent.parent
WB_SCRIPT = REPO_ROOT / "wb.py"

# Global knobs tweaked by CLI args so the tool reflects the requested scope.
TOOL_DEFAULT_LIMIT = 5
TOOL_INCLUDE_PROCESSED = False
PROMOTE_DEFAULT_DESCRIPTION: str | None = None
PROMOTE_DEFAULT_CONTACT: str | None = None
PROMOTE_DEFAULT_STATUS: str = "open"
PROMOTE_DEFAULT_FORCE: bool = False


def log(message: str) -> None:
    print(f"{LOG_PREFIX} {message}")


def _run_wb_command(args: list[str]) -> str:
    """Execute wb.py with the provided args and return combined stdout/stderr."""

    cmd = [sys.executable, str(WB_SCRIPT), *args]
    display = " ".join(shlex.quote(part) for part in ["wb", *args])
    log(f"Invoking CLI: {display}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    if proc.returncode != 0:
        details = stderr or stdout or "command produced no output"
        log(f"CLI exited with {proc.returncode}; propagating failure")
        raise RuntimeError(f"Command 'wb {' '.join(args)}' exited {proc.returncode}: {details}")
    log(
        "CLI finished successfully (stdout lines: {stdout_lines}, stderr lines: {stderr_lines})".format(
            stdout_lines=len(stdout.splitlines()) if stdout else 0,
            stderr_lines=len(stderr.splitlines()) if stderr else 0,
        )
    )
    if stdout:
        log("CLI stdout:\n" + stdout)
    if stderr:
        log("CLI stderr:\n" + stderr)
    if not stdout and not stderr:
        return "(command produced no output)"
    parts: list[str] = []
    if stdout:
        parts.append(stdout)
    if stderr:
        parts.append(f"[stderr]\n{stderr}")
    return "\n\n".join(parts)


def audit_auth_requests(limit: Optional[int] = None, include_processed: Optional[bool] = None) -> str:
    """Run the 'wb session list' CLI to audit authentication requests."""

    effective_limit = limit if limit not in (None, 0) else TOOL_DEFAULT_LIMIT
    effective_include = TOOL_INCLUDE_PROCESSED if include_processed is None else include_processed

    wb_args = ["session", "list"]
    if effective_include:
        wb_args.append("--all")
    if effective_limit and effective_limit > 0:
        wb_args.extend(["--limit", str(effective_limit)])

    return _run_wb_command(wb_args)


def promote_comment_to_request(
    comment_id: int,
    actor_username: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    contact_email: Optional[str] = None,
    force: Optional[bool] = None,
) -> str:
    args = [
        "promote-comment",
        "--comment-id",
        str(comment_id),
    ]
    summary = description or PROMOTE_DEFAULT_DESCRIPTION
    contact = contact_email or PROMOTE_DEFAULT_CONTACT
    status_value = status or PROMOTE_DEFAULT_STATUS
    effective_force = PROMOTE_DEFAULT_FORCE if force is None else force
    if actor_username:
        args.extend(["--actor", actor_username])
    if summary:
        args.extend(["--description", summary])
    if contact:
        args.extend(["--contact-email", contact])
    if status_value:
        args.extend(["--status", status_value])
    if effective_force:
        args.append("--force")
    args.extend(["--source", "mcp"])
    return _run_wb_command(args)


def _build_prompt(limit: int, include_processed: bool, promote_comment_id: Optional[int], promote_actor: Optional[str]) -> str:
    scope = "pending authentication requests only"
    if include_processed:
        scope = "all authentication requests, including processed ones"
    prompt = (
        "Use the available tools to triage WhiteBalloon operations. "
        "First, run `audit_auth_requests` to execute the real CLI against {scope} with a limit of {limit} rows. "
        "Summarize notable findings, then include the raw CLI output inside a fenced text code block."
    ).format(scope=scope, limit=limit)
    if promote_comment_id:
        prompt += (
            " After auditing, call `promote_comment_to_request` with comment_id={comment_id}"
        ).format(comment_id=promote_comment_id)
        if promote_actor:
            prompt += " and actor_username='{actor}'".format(actor=promote_actor)
        prompt += ". Include any helpful summary/contact overrides if needed."
    return prompt


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Dedalus Option A proof-of-concept that calls the wb session audit CLI via MCP tools."
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Dedalus model alias to use (default: openai/gpt-5-mini or DEDALUS_POC_MODEL env)",
    )
    parser.add_argument("--limit", type=int, default=5, help="Rows to request from the wb session list command")
    parser.add_argument(
        "--include-processed",
        action="store_true",
        help="Show processed/closed authentication requests instead of pending only",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Override the default instructions sent to Dedalus (advanced)",
    )
    parser.add_argument(
        "--promote-comment-id",
        type=int,
        default=None,
        help="If provided, instructs the agent to promote this comment via the MCP tool",
    )
    parser.add_argument(
        "--promote-actor",
        default=None,
        help="Username that should be passed to the promote tool (required if promoting)",
    )
    parser.add_argument(
        "--promote-description",
        default=None,
        help="Optional summary override suggestion for the promote tool",
    )
    parser.add_argument(
        "--promote-status",
        default="open",
        help="Default status suggestion for the promote tool",
    )
    parser.add_argument(
        "--promote-contact-email",
        default=None,
        help="Optional contact email suggestion for the promote tool",
    )
    parser.add_argument(
        "--promote-force",
        action="store_true",
        help="Allow the agent to bypass duplicate checks when promoting",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    log("Loading environment variables from .env")
    ensure_env_loaded()
    api_key = os.getenv("DEDALUS_API_KEY")
    if not api_key:
        print("Set DEDALUS_API_KEY in your .env before running this script.", file=sys.stderr)
        return 1

    global TOOL_DEFAULT_LIMIT, TOOL_INCLUDE_PROCESSED
    TOOL_DEFAULT_LIMIT = max(1, args.limit)
    TOOL_INCLUDE_PROCESSED = args.include_processed
    log(
        f"Configured tool scope → limit={TOOL_DEFAULT_LIMIT}, include_processed={TOOL_INCLUDE_PROCESSED}"
    )

    global PROMOTE_DEFAULT_DESCRIPTION, PROMOTE_DEFAULT_CONTACT, PROMOTE_DEFAULT_STATUS, PROMOTE_DEFAULT_FORCE
    PROMOTE_DEFAULT_DESCRIPTION = args.promote_description
    PROMOTE_DEFAULT_CONTACT = args.promote_contact_email
    PROMOTE_DEFAULT_STATUS = args.promote_status or "open"
    PROMOTE_DEFAULT_FORCE = args.promote_force

    instructions = args.prompt or _build_prompt(
        TOOL_DEFAULT_LIMIT,
        TOOL_INCLUDE_PROCESSED,
        args.promote_comment_id,
        args.promote_actor,
    )
    model = args.model or os.getenv("DEDALUS_POC_MODEL") or "openai/gpt-5-mini"
    log(f"Using Dedalus model: {model}")

    try:
        client = AsyncDedalus()
    except TypeError:  # pragma: no cover - backwards compatibility when api_key required
        client = AsyncDedalus(api_key=api_key)
    runner = DedalusRunner(client)
    run_id = start_logged_run(
        user_id=None,
        entity_type="cli",
        entity_id="dedalus_poc",
        model=model,
        prompt=instructions,
    )

    log("Starting Dedalus runner invocation")
    try:
        toolset = [audit_auth_requests]
        if args.promote_comment_id and args.promote_actor:
            toolset.append(promote_comment_to_request)
        response = await runner.run(
            input=instructions,
            model=model,
            tools=instrument_tools(toolset, run_id=run_id),
        )
    except Exception as exc:  # pragma: no cover - external dependency
        finalize_logged_run(run_id=run_id, response=None, status="error", error=str(exc))
        print(f"Dedalus request failed: {exc}", file=sys.stderr)
        return 1
    log("Dedalus runner finished; streaming final output")

    output = getattr(response, "final_output", None)
    if not output:
        outputs = getattr(response, "outputs", None)
        if isinstance(outputs, list) and outputs:
            output = "\n".join(str(item) for item in outputs)
        else:
            output = str(response)
    await finalize_from_response(run_id, response)
    print(output)
    return 0


def main() -> None:
    args = _parse_args()
    log("Dedalus CLI verification bootstrap starting")
    signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        exit_code = asyncio.run(run(args))
    except KeyboardInterrupt:
        log("Interrupted by Ctrl-C; stopping Dedalus verification")
        exit_code = 0
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
