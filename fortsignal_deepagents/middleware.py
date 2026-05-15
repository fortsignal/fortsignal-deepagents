"""FortSignal challenge/response middleware for Deep Agents.

This middleware intercepts risky tool calls (write_file, edit_file, execute,
task, write_todos) and routes them through FortSignal's challenge flow.

Two modes:
  - **Agent key** (autonomous): the middleware has an Ed25519 private key
    and signs challenges automatically using ``agentId``.
  - **Passkey** (human-in-the-loop): the middleware returns WebAuthn options
    and the user signs with their passkey in the browser.

Usage:
    from fortsignal_deepagents import FortSignalMiddleware

    middleware = FortSignalMiddleware(agent_id="my-agent", agent_key_path="key.json")
    agent = create_deep_agent(model="...", middleware=[middleware])
"""

from __future__ import annotations

import base64
import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from httpx import AsyncClient, HTTPError, HTTPStatusError
from langchain.agents.middleware.types import (
    AgentMiddleware,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tools that modify state or execute code — these require FortSignal approval
# ---------------------------------------------------------------------------
RISKY_TOOLS = frozenset({
    "write_file",
    "edit_file",
    "execute",
    "task",
    "write_todos",
    "eval",  # CodeInterpreterMiddleware (langchain-quickjs) — JS REPL, deepagents v0.6+
})

# How long to wait for the user to submit a signed challenge (seconds).
_CHALLENGE_TIMEOUT = 300  # 5 minutes to approve in browser + paste assertion

# Max retries for rate-limited (429) HTTP requests.
_MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# Retry helper for transient HTTP errors
# ---------------------------------------------------------------------------

async def _post_with_retry(
    client: AsyncClient,
    path: str,
    json_data: dict[str, Any],
    retries: int = _MAX_RETRIES,
) -> tuple[int, dict[str, Any]]:
    """POST to *path* with automatic back-off on 429 rate limits.

    Returns ``(status_code, parsed_json_body)`` on success.
    Raises ``HTTPStatusError`` for non-retryable errors.
    """
    for attempt in range(retries):
        resp = await client.post(path, json=json_data)
        if resp.status_code != 429 or attempt == retries - 1:
            resp.raise_for_status()
            return resp.status_code, resp.json()

        retry_after = _parse_retry_after(resp)
        logger.warning(
            "Rate limited on %s; retrying after %ss (attempt %d/%d)",
            path, retry_after, attempt + 1, retries,
        )
        import asyncio
        await asyncio.sleep(retry_after)

    resp.raise_for_status()
    return resp.status_code, resp.json()


def _parse_retry_after(resp) -> float:
    """Extract ``Retry-After`` header value as a float (seconds)."""
    raw = resp.headers.get("Retry-After", "1")
    try:
        return float(raw)
    except ValueError:
        return 1.0


# ---------------------------------------------------------------------------
# Data model for a pending challenge
# ---------------------------------------------------------------------------

@dataclass
class _PendingChallenge:
    """State retained between /challenge/start and /challenge/verify."""

    challenge_token: str
    tool_call_id: str
    tool_name: str
    args: dict[str, Any]
    user_id: str


# ---------------------------------------------------------------------------
# Helpers to map tool calls to FortSignal action model
# ---------------------------------------------------------------------------

def _tool_to_action(tool_name: str, args: dict[str, Any]) -> str:
    """Map a Deep Agent tool call to a FortSignal ``action`` string.

    Max 64 chars, alphanumeric + underscore/hyphen.
    """
    return tool_name


def _tool_to_recipient(tool_name: str, args: dict[str, Any]) -> str:
    """Derive a concise ``recipient`` from the tool call args.

    Max 256 chars.  Picks the most descriptive single field.
    """
    if tool_name == "write_file":
        return args.get("file_path", args.get("path", "unknown"))
    elif tool_name == "edit_file":
        return args.get("file_path", args.get("path", "unknown"))
    elif tool_name == "execute":
        cmd = args.get("command", "")
        return cmd[:256] if cmd else "execute"
    elif tool_name == "task":
        desc = args.get("description", "")
        return desc[:256] if desc else "sub_agent_task"
    elif tool_name == "write_todos":
        return "todos"
    return tool_name


# ---------------------------------------------------------------------------
# FortSignal Middleware
# ---------------------------------------------------------------------------

class FortSignalMiddleware(AgentMiddleware):
    """Middleware that requires FortSignal approval for risky tools.

    Two modes:
      - **Agent key** (autonomous): provide ``agent_id`` and
        ``agent_key_path`` (or env vars). The middleware signs Ed25519
        challenges automatically — no user interruption.
      - **Passkey** (human-in-the-loop): provide ``user_id``. WebAuthn
        options are returned to the agent; the user signs in the browser.

    Environment variables:
        FORTSIGNAL_API_KEY     : str  (required)
        FORTSIGNAL_BASE_URL    : str  (default: "https://api.fortsignal.com")
        FORTSIGNAL_AGENT_ID    : str  (for agent mode)
        FORTSIGNAL_AGENT_KEY   : str  (path to JSON file with privateKey)
        FORTSIGNAL_USER_ID     : str  (for passkey mode)
        FORTSIGNAL_LOG_LEVEL   : str  (default: "WARNING")
    """

    def __init__(
        self,
        user_id: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        agent_id: str | None = None,
        agent_key_path: str | None = None,
        http_client: AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("FORTSIGNAL_API_KEY", "")
        self.base_url = (
            base_url or os.getenv("FORTSIGNAL_BASE_URL", "https://api.fortsignal.com")
        ).rstrip("/")
        self.user_id = user_id or os.getenv("FORTSIGNAL_USER_ID", "")
        self.agent_id = agent_id or os.getenv("FORTSIGNAL_AGENT_ID", "")
        self.agent_key_path = agent_key_path or os.getenv("FORTSIGNAL_AGENT_KEY", "")
        self._client = http_client
        self._signing_key = None  # lazy-loaded Ed25519 private key

        # In-memory store of pending challenges, keyed by tool_call_id.
        self._pending: dict[str, _PendingChallenge] = {}

        log_level = os.getenv("FORTSIGNAL_LOG_LEVEL", "WARNING").upper()
        logging.getLogger(__name__).setLevel(getattr(logging, log_level, logging.WARNING))

    # ── Lazy HTTP client ────────────────────────────────────────────────

    @property
    def client(self) -> AsyncClient:
        if self._client is None:
            self._client = AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "User-Agent": "fortsignal-deepagents/0.1.0",
                },
                timeout=30,
            )
        return self._client

    # ── awrap_model_call: inject system-prompt context ──────────────────

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT] | ToolMessage | Command:
        if self.api_key:
            from deepagents.middleware._utils import append_to_system_message

            request.system_message = append_to_system_message(
                request.system_message,
                _SYSTEM_PROMPT_EXTENSION,
            )
        return await handler(request)

    # ── Agent signing key (Ed25519) ───────────────────────────────────

    def _load_signing_key(self):
        """Lazy-load the Ed25519 private key from ``agent_key_path``."""
        if self._signing_key is not None:
            return self._signing_key
        if not self.agent_key_path:
            return None
        try:
            with open(self.agent_key_path) as f:
                data = json.load(f)
            priv_b64 = data.get("privateKey", "")
            if not priv_b64:
                raise ValueError("No privateKey in agent key file")
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            priv_bytes = base64.urlsafe_b64decode(priv_b64 + "==")
            self._signing_key = Ed25519PrivateKey.from_private_bytes(priv_bytes)
            logger.info("Loaded Ed25519 signing key for agent %s", self.agent_id)
            return self._signing_key
        except Exception as exc:
            logger.warning("Failed to load agent signing key: %s", exc)
            return None

    # ── awrap_tool_call: intercept risky tools ──────────────────────────

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        tool_name = request.tool_call.get("name", "")
        tool_args: dict[str, Any] = request.tool_call.get("args", {}) or {}
        tool_call_id: str = request.tool_call.get("id", "")

        # Pass through for safe (read-only) tools
        if tool_name not in RISKY_TOOLS:
            return await handler(request)

        # ── Step 0: Check for a pending challenge assertion ────────────
        pending = self._pending.get(tool_call_id)
        if pending is not None:
            return await self._complete_challenge(request, pending, tool_args, handler)

        # No API key configured → friendly error
        missing = []
        if not self.api_key:
            missing.append("FORTSIGNAL_API_KEY")
        if missing:
            return ToolMessage(
                content=(
                    f"⚠️  Tool `{tool_name}` requires FortSignal approval, but "
                    f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not set.\n\n"
                    "Set the environment variable(s) and re-run, or remove "
                    "`FortSignalMiddleware` from the stack to skip checks."
                ),
                tool_call_id=tool_call_id,
                status="error",
            )

        # Determine mode: agent key (autonomous) vs passkey (human)
        use_agent = bool(self.agent_id and self._load_signing_key())

        # ── Step 1: Build action model and POST to /challenge/start ──
        action = _tool_to_action(tool_name, tool_args)
        recipient = _tool_to_recipient(tool_name, tool_args)

        challenge_payload: dict[str, Any] = {
            "action": action,
            "recipient": recipient,
            "metadata": {
                "tool": tool_name,
                "tool_call_id": tool_call_id,
                "args": tool_args,
            },
        }
        if use_agent:
            challenge_payload["agentId"] = self.agent_id
        else:
            if not self.user_id:
                return ToolMessage(
                    content=(
                        "⚠️  Tool `{tool_name}` requires FortSignal approval, but "
                        "no agent key or userId is configured.\n\n"
                        "Set FORTSIGNAL_AGENT_ID + FORTSIGNAL_AGENT_KEY for "
                        "autonomous mode, or FORTSIGNAL_USER_ID for passkey mode."
                    ),
                    tool_call_id=tool_call_id,
                    status="error",
                )
            challenge_payload["userId"] = self.user_id

        try:
            _, challenge_data = await _post_with_retry(
                self.client,
                "/challenge/start",
                challenge_payload,
            )
        except HTTPStatusError as exc:
            detail = _extract_error_detail(exc)
            logger.warning("/challenge/start %s: %s", exc.response.status_code, detail)
            return ToolMessage(
                content=f"FortSignal /challenge/start ({exc.response.status_code}): {detail}",
                tool_call_id=tool_call_id,
                status="error",
            )
        except HTTPError as exc:
            logger.warning("FortSignal network error: %s", exc)
            return ToolMessage(
                content=f"FortSignal network error: {exc}",
                tool_call_id=tool_call_id,
                status="error",
            )

        # Store challenge state for the verify step
        self._pending[tool_call_id] = _PendingChallenge(
            challenge_token=tool_call_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            args=tool_args,
            user_id=self.user_id,
        )

        # ── Step 2: Auto-sign (agent mode) or return challenge (passkey) ─
        if use_agent:
            logger.info(
                "Auto-signing challenge for %s (action=%s, recipient=%s)",
                tool_name, action, recipient,
            )
            return await self._auto_sign_and_verify(
                request, challenge_data, tool_call_id, tool_name, tool_args, handler,
            )

        # Passkey mode: return WebAuthn options to the agent
        logger.info(
            "Challenge created for %s (action=%s, recipient=%s)",
            tool_name, action, recipient,
        )

        return ToolMessage(
            content=json.dumps({
                "action": "fortsignal_challenge_required",
                "tool": tool_name,
                "tool_call_id": tool_call_id,
                "verification_type": "passkey",
                "webauthn_options": challenge_data,
                "instruction": (
                    f"FortSignal requires approval for `{tool_name}` on `{recipient}`.\n\n"
                    "To approve, sign the challenge with your passkey "
                    "then paste the WebAuthn assertion JSON into the next prompt. "
                    "The agent will then re-submit with "
                    "`_fortsignal_assertion` in the args."
                ),
            }),
            tool_call_id=tool_call_id,
            status="error",
        )

    # ── Step 3: Complete challenge (verify) ────────────────────────

    async def _complete_challenge(
        self,
        request: ToolCallRequest,
        pending: _PendingChallenge,
        tool_args: dict[str, Any],
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """Second half of the challenge flow — submit WebAuthn assertion."""
        assertion = tool_args.pop("_fortsignal_assertion", None)
        if not assertion:
            return ToolMessage(
                content=json.dumps({
                    "action": "fortsignal_challenge_required",
                    "tool": pending.tool_name,
                    "tool_call_id": pending.tool_call_id,
                    "verification_type": "passkey",
                    "instruction": (
                        "Sign the challenge with your passkey and provide the "
                        "WebAuthn assertion by setting `_fortsignal_assertion` "
                        "in the tool call args."
                    ),
                }),
                tool_call_id=pending.tool_call_id,
                status="error",
            )

        # If the assertion is a string, try to parse it as JSON
        if isinstance(assertion, str):
            try:
                assertion = json.loads(assertion)
            except json.JSONDecodeError:
                pass

        # Submit to /challenge/verify
        try:
            _, verify_data = await _post_with_retry(
                self.client,
                "/challenge/verify",
                assertion,
            )
        except HTTPStatusError as exc:
            status = exc.response.status_code
            detail = _extract_error_detail(exc)
            logger.warning("/challenge/verify %s: %s", status, detail)
            self._pending.pop(pending.tool_call_id, None)
            return ToolMessage(
                content=f"FortSignal /challenge/verify ({status}): {detail}",
                tool_call_id=pending.tool_call_id,
                status="error",
            )
        except HTTPError as exc:
            logger.warning("FortSignal verify network error: %s", exc)
            self._pending.pop(pending.tool_call_id, None)
            return ToolMessage(
                content=f"FortSignal verify network error: {exc}",
                tool_call_id=pending.tool_call_id,
                status="error",
            )

        # Clean up pending state
        self._pending.pop(pending.tool_call_id, None)

        decision = verify_data.get("decision")
        if decision != "allow":
            reason = verify_data.get("reason", "Challenge was denied")
            logger.info("Challenge denied for %s: %s", pending.tool_name, reason)
            return ToolMessage(
                content=f"FortSignal: {reason}",
                tool_call_id=pending.tool_call_id,
                status="error",
            )

        # ── Approved! Execute the real tool ─────────────────────────
        signal_id = verify_data.get("signalId", "unknown")
        logger.info(
            "Challenge approved for %s (signalId=%s)",
            pending.tool_name, signal_id,
        )

        clean_request = request.override(
            tool_call={
                **request.tool_call,
                "args": pending.args,
            },
        )
        return await handler(clean_request)

    # ── Auto-sign (agent mode) ──────────────────────────────────────

    async def _auto_sign_and_verify(
        self,
        request: ToolCallRequest,
        challenge_data: dict[str, Any],
        tool_call_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """Sign the challenge with the agent's Ed25519 key and verify."""
        challenge = challenge_data.get("challenge", "")
        if not challenge:
            return ToolMessage(
                content="FortSignal: no challenge in /challenge/start response",
                tool_call_id=tool_call_id,
                status="error",
            )

        key = self._load_signing_key()
        if key is None:
            return ToolMessage(
                content="FortSignal: agent signing key not loaded",
                tool_call_id=tool_call_id,
                status="error",
            )

        # Sign the challenge bytes
        challenge_bytes = base64.urlsafe_b64decode(challenge + "==")
        signature = key.sign(challenge_bytes)
        sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()

        # POST to /challenge/verify
        verify_payload = {
            "agentId": self.agent_id,
            "challenge": challenge,
            "signature": sig_b64,
        }
        try:
            _, verify_data = await _post_with_retry(
                self.client,
                "/challenge/verify",
                verify_payload,
            )
        except HTTPStatusError as exc:
            status = exc.response.status_code
            detail = _extract_error_detail(exc)
            logger.warning("/challenge/verify %s: %s", status, detail)
            return ToolMessage(
                content=f"FortSignal /challenge/verify ({status}): {detail}",
                tool_call_id=tool_call_id,
                status="error",
            )
        except HTTPError as exc:
            logger.warning("FortSignal verify network error: %s", exc)
            return ToolMessage(
                content=f"FortSignal verify network error: {exc}",
                tool_call_id=tool_call_id,
                status="error",
            )

        decision = verify_data.get("decision")
        if decision != "allow":
            reason = verify_data.get("reason", "Challenge was denied")
            logger.info("Challenge denied for %s: %s", tool_name, reason)
            return ToolMessage(
                content=f"FortSignal: {reason}",
                tool_call_id=tool_call_id,
                status="error",
            )

        signal_id = verify_data.get("signalId", "unknown")
        logger.info(
            "Challenge approved for %s (signalId=%s, verifiedBy=agent)",
            tool_name, signal_id,
        )

        # Execute the tool via request.override (preserves original args)
        clean_request = request.override(
            tool_call={
                **request.tool_call,
                "args": tool_args,
            },
        )
        return await handler(clean_request)


# ── Helpers ────────────────────────────────────────────────────────────────


def _extract_error_detail(exc: HTTPStatusError) -> str:
    """Pull a human-readable error message from an HTTP error response."""
    try:
        body = exc.response.json()
        return str(body.get("detail") or body.get("error") or body.get("message") or body)
    except Exception:
        return exc.response.text[:500]


_SYSTEM_PROMPT_EXTENSION = """
## FortSignal Security

This agent is protected by FortSignal's cryptographic challenge/response
security. High-risk tools (write_file, edit_file, execute, task, write_todos)
are intercepted by `FortSignalMiddleware` and require WebAuthn passkey approval
before they can execute.

### When a tool call is blocked

The middleware returns a `ToolMessage` with `status="error"` and a JSON payload
in `content` containing:

- `action`: always `"fortsignal_challenge_required"`
- `tool`: the name of the tool that was blocked
- `tool_call_id`: the original tool call ID
- `verification_type`: `"passkey"`
- `webauthn_options`: the WebAuthn `PublicKeyCredentialRequestOptions` (pass to
  `startAuthentication()` from `@simplewebauthn/browser`)
- `instruction`: human-readable instructions for the user

### To complete the challenge

1. The user signs the challenge with their passkey via the browser.
2. The user copies the `AuthenticationResponseJSON` and pastes it back.
3. The agent re-submits the tool call with `_fortsignal_assertion` in the args
   (either the raw JSON object or the stringified version).
4. The middleware POSTs the assertion to `/challenge/verify`. If
   `"decision": "allow"` the original tool executes normally.
"""
