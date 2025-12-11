#!/usr/bin/env python3
"""Helper to verify access to the MIT OpenWebUI Chat Completions API."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests

DEFAULT_BASE_URL = "https://llms-dev-1.mit.edu"
DEFAULT_PROMPT = "Hello from whiteballoon! Please confirm you are reachable with a short reply."
API_ENV_NAMES = ["OPENWEBUI_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY"]
MODEL_ENV_NAMES = ["OPENWEBUI_MODEL", "LLM_MODEL", "OPENAI_MODEL"]


def env_lookup(names: list[str]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send a simple chat.completions request to validate API access.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--api-key",
        default=env_lookup(API_ENV_NAMES),
        help="API key from OpenWebUI → Settings → Account. Default is the first populated env var.",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENWEBUI_BASE_URL", DEFAULT_BASE_URL),
        help="Base URL of your OpenWebUI instance (without the trailing /api/v1 part).",
    )
    parser.add_argument(
        "--model",
        default=env_lookup(MODEL_ENV_NAMES),
        help="Model identifier exposed by OpenWebUI. Default is the first populated env var.",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="Text that will be sent as the user message in the health-check request.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available models (GET /api/v1/models) before attempting the request.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prepared payload without sending it.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification (useful only for dev/test with self-signed certs).",
    )
    return parser


def list_models(base_url: str, api_key: str, timeout: float, verify: bool) -> None:
    url = base_url.rstrip("/") + "/api/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    response = requests.get(url, headers=headers, timeout=timeout, verify=verify)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        print(f"Failed to list models: {exc}\nBody:\n{response.text}", file=sys.stderr)
        raise

    data = response.json()
    models = data.get("data") or data.get("models") or []
    if not models:
        print("No models returned.")
        return

    print("Available models:")
    for item in models:
        # Works for either {"id": ...} or {"name": ...}
        identifier = item.get("id") or item.get("name") or str(item)
        print(f"- {identifier}")


def build_payload(model: str, prompt: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a concise assistant used for health checks."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }


def send_chat(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    timeout: float,
    verify: bool,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/api/v1/chat/completions"
    payload = build_payload(model=model, prompt=prompt)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = requests.post(url, headers=headers, json=payload, timeout=timeout, verify=verify)
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        text = response.text
        print(f"Request failed: {exc}\nResponse body:\n{text}", file=sys.stderr)
        raise

    return response.json()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.api_key:
        parser.error(
            "Missing API key. Provide --api-key or set one of: " + ", ".join(API_ENV_NAMES)
        )

    if not args.model:
        parser.error(
            "Missing model name. Provide --model or set one of: " + ", ".join(MODEL_ENV_NAMES)
        )

    base_url = args.base_url.rstrip("/")

    if args.list_models:
        list_models(base_url, args.api_key, args.timeout, verify=not args.insecure)

    payload = build_payload(args.model, args.prompt)

    if args.dry_run:
        print("Dry run — request payload:")
        print(json.dumps({"endpoint": base_url + "/api/v1/chat/completions", "payload": payload}, indent=2))
        return

    response = send_chat(
        base_url=base_url,
        api_key=args.api_key,
        model=args.model,
        prompt=args.prompt,
        timeout=args.timeout,
        verify=not args.insecure,
    )

    print("Model reply:")
    try:
        content = response["choices"][0]["message"]["content"]
    except Exception:  # pragma: no cover - keep fallback minimal
        content = None

    if content:
        print(content)
    else:
        print("<no content field in response>")

    print("\nFull JSON response:")
    print(json.dumps(response, indent=2))


if __name__ == "__main__":
    main()
