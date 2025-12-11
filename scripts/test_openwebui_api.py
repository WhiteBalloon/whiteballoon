#!/usr/bin/env python3
"""Send a quick test prompt to the MIT OpenWebUI server."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx

DEFAULT_ENDPOINT = "https://llms-dev-1.mit.edu/api/v1/chat/completions"
DEFAULT_PROMPT = "Hello from whiteballoon. Please respond with a short sentence confirming you are reachable."
CHECK_ENV_VARS = ("OPENWEBUI_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY")
MODEL_ENV_VARS = ("OPENWEBUI_MODEL", "LLM_MODEL", "OPENAI_MODEL")


def _env_lookup(keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = os.environ.get(key)
        if value:
            return value
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Send a simple chat.completions request to the OpenWebUI server to make sure your "
            "API key works."
        )
    )
    parser.add_argument(
        "--api-key",
        default=_env_lookup(CHECK_ENV_VARS),
        help="API key from OpenWebUI Settings → Account. Defaults to the first populated env var: "
        f"{', '.join(CHECK_ENV_VARS)}.",
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help=(
            "Full chat completions endpoint. Override if you have a different host or prefer a "
            "custom path."
        ),
    )
    parser.add_argument(
        "--model",
        default=_env_lookup(MODEL_ENV_VARS),
        help=(
            "Model identifier exposed by OpenWebUI. Defaults to the first populated env var: "
            f"{', '.join(MODEL_ENV_VARS)}."
        ),
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="Text for the user message in the test request.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP client timeout in seconds."
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification (useful only with self-signed certs).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the payload without sending it."
    )
    return parser.parse_args()


def _build_payload(model: str, prompt: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a concise assistant used for health checks."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }


def send_request(
    endpoint: str,
    api_key: str,
    payload: dict[str, Any],
    timeout: float,
    verify: bool,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=timeout, verify=verify) as client:
        response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


def main() -> None:
    args = parse_args()

    if not args.api_key:
        print(
            "Missing API key. Provide --api-key or set one of: " + ", ".join(CHECK_ENV_VARS),
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.model:
        print(
            "Missing model name. Provide --model or set one of: " + ", ".join(MODEL_ENV_VARS),
            file=sys.stderr,
        )
        sys.exit(1)

    payload = _build_payload(model=args.model, prompt=args.prompt)

    if args.dry_run:
        print("Dry run — request payload:")
        print(json.dumps({"endpoint": args.endpoint, "payload": payload}, indent=2))
        return

    print(f"Sending chat.completions request to {args.endpoint} with model '{args.model}'...")

    try:
        data = send_request(
            endpoint=args.endpoint,
            api_key=args.api_key,
            payload=payload,
            timeout=args.timeout,
            verify=not args.insecure,
        )
    except httpx.HTTPStatusError as exc:
        print(
            f"Request failed with status {exc.response.status_code}: {exc.response.text}",
            file=sys.stderr,
        )
        sys.exit(2)
    except httpx.HTTPError as exc:
        print(f"HTTP error: {exc}", file=sys.stderr)
        sys.exit(2)

    choices = data.get("choices", [])
    if not choices:
        print("Got response but it did not contain any choices:")
        print(json.dumps(data, indent=2))
        sys.exit(3)

    message = choices[0].get("message", {})
    content = message.get("content", "<no content>")

    print("Model replied with:\n")
    print(content)
    print("\nFull JSON response:\n")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
