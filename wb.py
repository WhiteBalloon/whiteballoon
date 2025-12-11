#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import errno
import io
import json
import os
import platform
import secrets
import shutil
import signal
import socket
import subprocess
import sys
from pathlib import Path

from app.env import ensure_env_loaded

ensure_env_loaded()

from app.hub.config import DEFAULT_STORAGE_DIR, hash_token


# -------- Logging helpers --------

def _supports_color() -> bool:
    if platform.system() == "Windows":
        return False  # keep simple; wrappers provide color
    return sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _supports_color() else text


def info(msg: str) -> None:
    print(_c("0;34", f"[INFO] {msg}"))


def warn(msg: str) -> None:
    print(_c("1;33", f"[WARN] {msg}"))


def error(msg: str) -> None:
    print(_c("0;31", f"[ERROR] {msg}"), file=sys.stderr)


# -------- Paths and execution helpers --------

SCRIPT_DIR = Path(__file__).resolve().parent
VENV_DIR = SCRIPT_DIR / ".venv"
DEV_TOOL = SCRIPT_DIR / "tools" / "dev.py"
DEDALUS_POC = SCRIPT_DIR / "tools" / "dedalus_cli_verification.py"
DEDALUS_LOG_MAINT = SCRIPT_DIR / "tools" / "dedalus_log_maintenance.py"
SIGNAL_IMPORT_MODULE = "app.tools.signal_import"
CHAT_INDEX_MODULE = "app.tools.request_chat_index"
CHAT_EMBED_MODULE = "app.tools.request_chat_embeddings"
COMMENT_LLM_MODULE = "app.tools.comment_llm_processing"
SIGNAL_PROFILE_MODULE = "app.tools.signal_profile_snapshot_cli"
PROFILE_GLAZE_MODULE = "app.tools.profile_glaze_cli"
COMMENT_PROMOTION_MODULE = "app.tools.comment_promotion_cli"
COMMENT_PROMOTION_BATCH_MODULE = "app.tools.comment_promotion_batch"


def python_in_venv() -> Path:
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def run(argv: list[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(argv, check=check)


# -------- Environment bootstrap --------

def create_venv() -> None:
    if python_in_venv().exists():
        return
    info("Creating virtual environment at .venv")
    subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)


def ensure_pip(venv_python: Path) -> None:
    try:
        subprocess.run([str(venv_python), "-m", "pip", "--version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    except Exception:
        info("Bootstrapping pip in virtual environment")
    # Try ensurepip
    result = subprocess.run([str(venv_python), "-m", "ensurepip", "--upgrade"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode != 0:
        error(
            "Virtualenv missing pip and ensurepip is unavailable. On Debian/Ubuntu, install 'python3-venv'. On Windows, repair Python install to enable pip."
        )
        sys.exit(1)


def upgrade_pip(venv_python: Path) -> None:
    subprocess.run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], check=True)


def editable_install(venv_python: Path) -> None:
    subprocess.run([str(venv_python), "-m", "pip", "install", "-e", str(SCRIPT_DIR)], check=True)


def create_env_file() -> None:
    env_file = SCRIPT_DIR / ".env"
    env_example = SCRIPT_DIR / ".env.example"
    if env_file.exists():
        return
    if env_example.exists():
        shutil.copyfile(env_example, env_file)
        info("Created .env from .env.example")
    else:
        warn(".env.example not found; skipping .env creation")


# -------- Dev tool integration --------

def ensure_cli_ready(python_exe: Path) -> bool:
    code = (
        "try:\n"
        "    import fastapi\n"
        "    import click\n"
        "except Exception:\n"
        "    raise SystemExit(1)\n"
    )
    result = subprocess.run([str(python_exe), "-c", code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


@contextlib.contextmanager
def _suppress_ctrl_c_echo(enabled: bool):
    if not enabled:
        yield
        return
    stream = getattr(sys, "stdin", None)
    if stream is None:
        yield
        return
    try:
        fd = stream.fileno()
        is_tty = stream.isatty()
    except (io.UnsupportedOperation, AttributeError, ValueError):
        yield
        return
    if not is_tty:
        yield
        return
    try:
        import termios  # type: ignore
    except ImportError:
        yield
        return
    try:
        original = termios.tcgetattr(fd)
    except termios.error:
        yield
        return
    updated = original.copy()
    updated[3] &= ~termios.ECHOCTL
    try:
        termios.tcsetattr(fd, termios.TCSANOW, updated)
    except termios.error:
        yield
        return
    try:
        yield
    finally:
        with contextlib.suppress(termios.error):
            termios.tcsetattr(fd, termios.TCSANOW, original)


def _run_process(
    cmd: list[str], *, env: dict[str, str] | None = None, graceful_interrupt: bool = False, interrupt_message: str | None = None
) -> int:
    with _suppress_ctrl_c_echo(graceful_interrupt):
        proc = subprocess.Popen(cmd, env=env)
        try:
            return proc.wait()
        except KeyboardInterrupt:
            with contextlib.suppress(ProcessLookupError):
                proc.send_signal(signal.SIGINT)
            if not graceful_interrupt:
                raise
            try:
                proc.wait()
            except KeyboardInterrupt:
                proc.kill()
                raise
            if interrupt_message:
                info(interrupt_message)
            return 0


def dev_invoke(venv_python: Path, *args: str, graceful_interrupt: bool = False, interrupt_message: str | None = None) -> int:
    """Invoke the dev tool inside the venv, optionally suppressing Ctrl-C tracebacks."""

    cmd = [str(venv_python), str(DEV_TOOL), *args]
    return _run_process(cmd, graceful_interrupt=graceful_interrupt, interrupt_message=interrupt_message)


def cmd_hub(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb hub", description="Manage the sync hub service")
    parser.add_argument("action", choices=["serve", "admin-token"], nargs="?")
    parser.add_argument("--config", dest="config", default=str(SCRIPT_DIR / ".sync" / "hub_config.json"), help="Path to hub config (WB_HUB_CONFIG)")
    parser.add_argument("--host", dest="host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", dest="port", type=int, default=9100, help="Port to bind")
    parser.add_argument("--token-name", dest="token_name", default="primary", help="Identifier when creating admin tokens")
    parser.add_argument("--no-reload", dest="reload", action="store_false", help="Disable autoreload (enabled by default)")
    parser.set_defaults(reload=True)
    if not args or args[0] in {"help", "--help", "-h"}:
        parser.print_help()
        return 0

    ns = parser.parse_args(args)

    if ns.action == "admin-token":
        return _create_hub_admin_token(Path(ns.config), ns.token_name)

    if ns.action is None:
        parser.print_help()
        return 0

    vpy = python_in_venv()
    if not vpy.exists():
        warn("Virtualenv missing. Run './wb setup' first.")
        return 1
    env = os.environ.copy()
    env.setdefault("WB_HUB_CONFIG", ns.config)
    cmd = [
        str(vpy),
        "-m",
        "uvicorn",
        "app.hub:hub_app",
        "--host",
        ns.host,
        "--port",
        str(ns.port),
    ]
    if ns.reload:
        cmd.append("--reload")
    info(f"Starting hub on {ns.host}:{ns.port}")
    return _run_process(cmd, env=env, graceful_interrupt=True, interrupt_message="Hub stopped")


def cmd_import_signal_group(args: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="wb import-signal-group",
        description="Import a Signal Desktop group export into the local database",
    )
    parser.add_argument(
        "--export-path",
        required=True,
        help="Path to the folder (on Windows or /mnt/c) created by signal-export",
    )
    parser.add_argument(
        "--group-name",
        help="Optional friendly name override for the group",
    )
    parser.add_argument(
        "--log-path",
        default="signal_group_import.log",
        help="Where to write the import log (default: signal_group_import.log)",
    )
    parser.add_argument(
        "--skip-attachments",
        action="store_true",
        help="Skip copying attachment metadata while seeding",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and log without writing to the database",
    )
    if not args or args[0] in {"-h", "--help", "help"}:
        parser.print_help()
        return 0

    ns = parser.parse_args(args)

    vpy = python_in_venv()
    if not vpy.exists():
        warn("Virtualenv missing. Run './wb setup' first.")
        return 1
    if not ensure_cli_ready(vpy):
        warn("Dependencies missing. Run './wb setup' first.")
        return 1

    cmd = [
        str(vpy),
        "-m",
        SIGNAL_IMPORT_MODULE,
        "--export-path",
        ns.export_path,
        "--log-path",
        ns.log_path,
    ]
    if ns.group_name:
        cmd.extend(["--group-name", ns.group_name])
    if ns.skip_attachments:
        cmd.append("--skip-attachments")
    if ns.dry_run:
        cmd.append("--dry-run")
    info("Launching Signal group importer (stub)")
    return _run_process(cmd)


def cmd_signal_profile(args: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="wb signal-profile",
        description="Manage Signal profile snapshot utilities",
    )
    parser.add_argument(
        "subcommand",
        nargs="?",
        default="snapshot",
        help="Subcommand to run (default: snapshot)",
    )
    if not args or args[0] in {"-h", "--help", "help"}:
        parser.print_help()
        return 0

    ns = parser.parse_args(args[:1])
    vpy = python_in_venv()
    if not vpy.exists():
        warn("Virtualenv missing. Run './wb setup' first.")
        return 1
    if not ensure_cli_ready(vpy):
        warn("Dependencies missing. Run './wb setup' first.")
        return 1

    cmd = [str(vpy), "-m", SIGNAL_PROFILE_MODULE, ns.subcommand, *args[1:]]
    info("Launching Signal profile utility")
    return _run_process(cmd)


def cmd_profile_glaze(args: list[str]) -> int:
    vpy = python_in_venv()
    if not ensure_cli_ready(vpy):
        warn("Dependencies missing. Run './wb setup' first.")
        return 1
    cmd = [str(vpy), "-m", PROFILE_GLAZE_MODULE, *args]
    info("Running profile glazing pipeline")
    return _run_process(cmd)


def cmd_chat_index(args: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="wb chat-index",
        description="Rebuild request chat caches and optionally run LLM tagging",
    )
    if not args or args[0] in {"-h", "--help", "help"}:
        parser.print_help()
        return 0

    vpy = python_in_venv()
    if not vpy.exists():
        warn("Virtualenv missing. Run './wb setup' first.")
        return 1
    if not ensure_cli_ready(vpy):
        warn("Dependencies missing. Run './wb setup' first.")
        return 1

    cmd = [str(vpy), "-m", CHAT_INDEX_MODULE, *args]
    info("Reindexing request chat caches")
    return _run_process(cmd)


def cmd_chat_embed(args: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="wb chat-embed",
        description="Generate embedding caches for request chats",
    )
    if not args or args[0] in {"-h", "--help", "help"}:
        parser.print_help()
        return 0

    vpy = python_in_venv()
    if not vpy.exists():
        warn("Virtualenv missing. Run './wb setup' first.")
        return 1
    if not ensure_cli_ready(vpy):
        warn("Dependencies missing. Run './wb setup' first.")
        return 1

    cmd = [str(vpy), "-m", CHAT_EMBED_MODULE, *args]
    info("Generating semantic chat embeddings")
    return _run_process(cmd)


def cmd_comment_llm(args: list[str]) -> int:
    vpy = python_in_venv()
    if not vpy.exists():
        warn("Virtualenv missing. Run './wb setup' first.")
        return 1
    if not ensure_cli_ready(vpy):
        warn("Dependencies missing. Run './wb setup' first.")
        return 1

    passthrough = list(args)
    if not passthrough:
        passthrough = ["--help"]
    elif passthrough[0] in {"-h", "--help", "help"}:
        passthrough = ["--help", *passthrough[1:]]

    cmd = [str(vpy), "-m", COMMENT_LLM_MODULE, *passthrough]
    info("Running comment LLM batch planner/executor")
    return _run_process(cmd)


def cmd_promote_comment(args: list[str]) -> int:
    vpy = python_in_venv()
    if not vpy.exists():
        warn("Virtualenv missing. Run './wb setup' first.")
        return 1
    if not ensure_cli_ready(vpy):
        warn("Dependencies missing. Run './wb setup' first.")
        return 1

    cmd = [str(vpy), "-m", COMMENT_PROMOTION_MODULE, *args]
    info("Promoting comment via CLI helper")
    return _run_process(cmd)


def cmd_promote_comment_batch(args: list[str]) -> int:
    vpy = python_in_venv()
    if not vpy.exists():
        warn("Virtualenv missing. Run './wb setup' first.")
        return 1
    if not ensure_cli_ready(vpy):
        warn("Dependencies missing. Run './wb setup' first.")
        return 1
    cmd = [str(vpy), "-m", COMMENT_PROMOTION_BATCH_MODULE, *args]
    info("Running comment promotion queue worker")
    return _run_process(cmd)


def cmd_dedalus(args: list[str]) -> int:
    if not args or args[0] in {"-h", "--help", "help"}:
        print("Usage: wb dedalus <subcommand> [options]")
        print("  test          Run the Step 1 verification script (passes remaining args through)")
        print("  purge-logs    Delete log rows older than the retention window")
        return 0
    subcommand, *passthrough = args
    vpy = python_in_venv()
    if not vpy.exists():
        warn("Virtualenv missing. Run './wb setup' first.")
        return 1
    if subcommand == "test":
        if not DEDALUS_POC.exists():
            error("Missing Dedalus verification script. Expected tools/dedalus_cli_verification.py")
            return 1
        info("Launching Dedalus CLI verification script")
        cmd = [str(vpy), str(DEDALUS_POC), *passthrough]
        return _run_process(
            cmd,
            graceful_interrupt=True,
            interrupt_message="Dedalus verification stopped",
        )
    if subcommand == "purge-logs":
        if not DEDALUS_LOG_MAINT.exists():
            error("Missing Dedalus log maintenance script.")
            return 1
        info("Purging Dedalus logs")
        cmd = [str(vpy), str(DEDALUS_LOG_MAINT), "purge", *passthrough]
        return _run_process(cmd)
    error(f"Unknown dedalus subcommand: {subcommand}")
    return 1


def _create_hub_admin_token(config_path: Path, token_name: str) -> int:
    token = secrets.token_hex(32)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        data = {"storage_dir": str(DEFAULT_STORAGE_DIR), "peers": []}
    admin_tokens = data.get("admin_tokens") or []
    admin_tokens = [entry for entry in admin_tokens if entry.get("name") != token_name]
    admin_tokens.append({"name": token_name, "token_hash": hash_token(token)})
    data["admin_tokens"] = admin_tokens
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    info(f"Wrote admin token '{token_name}' to {config_path}")
    print("Share this token securely:")
    print(f"  {token}")
    return 0


# -------- CLI handlers --------

def cmd_setup(_args: argparse.Namespace) -> int:
    create_venv()
    vpy = python_in_venv()
    ensure_pip(vpy)
    info("Installing project dependencies")
    upgrade_pip(vpy)
    editable_install(vpy)
    create_env_file()
    info("Initializing database")
    rc = dev_invoke(vpy, "init-db")
    if rc != 0:
        error("Database initialization failed")
        return rc
    info("Setup complete")
    return 0


def cmd_update_env(args: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="wb update-env", description="Sync .env with .env.example defaults")
    parser.add_argument("--env-path", default=str(SCRIPT_DIR / ".env"), help="Path to the .env file")
    parser.add_argument("--example-path", default=str(SCRIPT_DIR / ".env.example"), help="Path to .env.example")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    ns = parser.parse_args(args)

    script = SCRIPT_DIR / "tools" / "update_env_defaults.py"
    if not script.exists():
        error(f"Missing helper script: {script}")
        return 1

    cmd = [sys.executable, str(script), "--env-path", ns.env_path, "--example-path", ns.example_path]
    if ns.dry_run:
        cmd.append("--dry-run")
    return subprocess.call(cmd)


def cmd_known(known_cmd: str, passthrough: list[str], *, graceful_interrupt: bool = False, interrupt_message: str | None = None) -> int:
    vpy = python_in_venv()
    if not ensure_cli_ready(vpy):
        warn("Dependencies missing. Run './wb setup' first.")
        print()
        print_help()
        return 1
    return dev_invoke(vpy, known_cmd, *passthrough, graceful_interrupt=graceful_interrupt, interrupt_message=interrupt_message)


def _running_in_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in Path("/proc/sys/kernel/osrelease").read_text().lower()
    except FileNotFoundError:
        return False


def _parse_host_port(args: list[str]) -> tuple[str, int]:
    host: str | None = None
    host_explicit = False
    port = 8000
    it = iter(range(len(args)))
    for i in it:
        a = args[i]
        if a == "--host" and i + 1 < len(args):
            host = args[i + 1]
            host_explicit = True
            next(it, None)
        elif a.startswith("--host="):
            host = a.split("=", 1)[1]
            host_explicit = True
        elif a == "--port" and i + 1 < len(args):
            try:
                port = int(args[i + 1])
            except ValueError:
                pass
            next(it, None)
        elif a.startswith("--port="):
            try:
                port = int(a.split("=", 1)[1])
            except ValueError:
                pass
    if not host_explicit or not host:
        host = "0.0.0.0" if _running_in_wsl() else "127.0.0.1"
    return host, port


def _port_available(host: str, port: int) -> tuple[bool, OSError | None]:
    try:
        addrinfo = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        return False, exc
    last_exc: OSError | None = None
    for family, socktype, proto, _, sockaddr in addrinfo:
        try:
            with socket.socket(family, socktype, proto) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(sockaddr)
            return True, None
        except OSError as exc:
            last_exc = exc
    return False, last_exc


def preflight_runserver(passthrough: list[str]) -> bool:
    host, port = _parse_host_port(passthrough)
    available, exc = _port_available(host, port)
    if available:
        return True
    if exc is None:
        warn(f"Unable to bind {host}:{port} for an unknown reason")
        return False
    if exc.errno == errno.EADDRINUSE:
        warn(f"Address already in use: {host}:{port}")
        print("Try one of the following:")
        print(f"  - Choose a different port: wb runserver --port {port + 1}")
        if _running_in_wsl():
            print(f"  - (WSL) Find process: lsof -i :{port} -sTCP:LISTEN")
            print(f"  - (WSL) Kill process: fuser -k {port}/tcp")
            print(f"  - (Windows) Find process: netstat -ano ^| findstr :{port}")
            print("  - (Windows) Kill: taskkill /PID <pid> /F")
        elif platform.system() == "Windows":
            print(f"  - Find process: netstat -ano ^| findstr :{port}")
            print("  - Then terminate via Task Manager or: taskkill /PID <pid> /F")
        else:
            print(f"  - Find process: lsof -i :{port} -sTCP:LISTEN")
            print(f"  - Kill process: fuser -k {port}/tcp")
        return False
    warn(f"Failed to check {host}:{port}: {exc}")
    return False


def print_help() -> None:
    print("WhiteBalloon CLI Wrapper")
    print("Usage: wb <command> [options]")
    print()
    print("Core commands:")
    print("  setup                 Create virtualenv, install dependencies, and initialize the database")
    print("  runserver [--opts]    Start the development server")
    print("  init-db               Initialize the SQLite database")
    print("  create-admin USER     Promote a user to admin")
    print("  create-invite [opts]  Generate invite tokens")
    print("  import-signal-group   Import a Signal Desktop group export (local seed)")
    print("  chat-index [opts]     Reindex request chats + optional LLM tagging")
    print("  chat-embed [opts]     Build semantic embeddings for request chats")
    print("  comment-llm [opts]    Plan or run batched comment processing via LLM")
    print("  profile-glaze [opts]  Analyze comments + glaze Signal bios in one shot")
    print("  session <command>     Inspect or manage authentication sessions")
    print("  dedalus test [opts]   Run the Dedalus verification script")
    print("  sync <command> [opts] Manual sync utilities (export/import)")
    print("  skins <command>       Build or watch skin CSS bundles")
    print("  hub serve [opts]      Run the sync hub (uvicorn)")
    print("  update-env [opts]     Add missing values from .env.example")
    print("  version               Display CLI version info")
    print("  help                  Show this help message")
    print()
    print("Any other arguments are forwarded to the underlying Click CLI in tools/dev.py.")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False)
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("help")
    subparsers.add_parser("version")
    subparsers.add_parser("setup")
    subparsers.add_parser("runserver")
    subparsers.add_parser("init-db")
    subparsers.add_parser("create-admin")
    subparsers.add_parser("create-invite")
    subparsers.add_parser("session")
    subparsers.add_parser("dedalus")
    subparsers.add_parser("import-signal-group")
    subparsers.add_parser("chat-index")
    subparsers.add_parser("chat-embed")
    subparsers.add_parser("comment-llm")
    subparsers.add_parser("promote-comment")
    subparsers.add_parser("promote-comment-batch")
    subparsers.add_parser("profile-glaze")
    subparsers.add_parser("sync")
    subparsers.add_parser("skins")
    subparsers.add_parser("hub")
    subparsers.add_parser("update-env")
    subparsers.add_parser("signal-profile")

    # Parse only the command; leave the rest as passthrough
    known, passthrough = (argv[:1], argv[1:]) if argv else ([], [])
    ns, _ = parser.parse_known_args(known)

    if not argv or ns.command in (None, "help"):
        print_help()
        return 0

    if ns.command == "version":
        print("WhiteBalloon CLI 0.1.0")
        return 0

    if ns.command == "setup":
        return cmd_setup(ns)

    if ns.command == "hub":
        return cmd_hub(passthrough)

    if ns.command == "dedalus":
        return cmd_dedalus(passthrough)

    if ns.command == "update-env":
        return cmd_update_env(passthrough)

    if ns.command == "import-signal-group":
        return cmd_import_signal_group(passthrough)
    if ns.command == "signal-profile":
        return cmd_signal_profile(passthrough)

    if ns.command == "chat-index":
        return cmd_chat_index(passthrough)
    if ns.command == "chat-embed":
        return cmd_chat_embed(passthrough)
    if ns.command == "comment-llm":
        return cmd_comment_llm(passthrough)
    if ns.command == "promote-comment":
        return cmd_promote_comment(passthrough)
    if ns.command == "promote-comment-batch":
        return cmd_promote_comment_batch(passthrough)
    if ns.command == "profile-glaze":
        return cmd_profile_glaze(passthrough)

    # Known commands path
    if ns.command in {"runserver", "init-db", "create-admin", "create-invite", "session", "sync", "skins"}:
        if ns.command in {"session", "sync"}:
            if not passthrough:
                passthrough = ["--help"]
            elif passthrough[0] == "help":
                passthrough = ["--help", *passthrough[1:]]
        if ns.command == "skins" and not passthrough:
            passthrough = ["--help"]
        if ns.command == "runserver" and not preflight_runserver(passthrough):
            return 1
        graceful_interrupt = ns.command == "runserver"
        interrupt_message = "Server stopped" if graceful_interrupt else None
        rc = cmd_known(
            ns.command,
            passthrough,
            graceful_interrupt=graceful_interrupt,
            interrupt_message=interrupt_message,
        )
        if rc != 0 and ns.command not in {"runserver", "sync"}:
            warn("Command failed. Run './wb setup' first if not done.")
            print()
            print_help()
        return rc

    # Default passthrough to dev tool
    vpy = python_in_venv()
    if not ensure_cli_ready(vpy):
        warn("Dependencies missing. Run './wb setup' first.")
        print()
        print_help()
        return 1
    rc = dev_invoke(vpy, *argv)
    if rc != 0:
        warn(f"Command '{argv[0]}' not recognized or failed.")
        print()
        print_help()
    return rc


if __name__ == "__main__":
    sys.exit(main())
