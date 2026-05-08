"""FortSignal-secured Deep Agents — cryptographically safe coding agents.

This package provides a middleware that intercepts risky tool calls
(write_file, edit_file, execute, task, write_todos) and routes them through
FortSignal's cryptographic challenge flow.

Two modes:
  - **Agent key** (autonomous): set ``FORTSIGNAL_AGENT_ID`` and
    ``FORTSIGNAL_AGENT_KEY``. The middleware signs Ed25519 challenges
    automatically — no user interruption.
  - **Passkey** (human-in-the-loop): set ``FORTSIGNAL_USER_ID``. WebAuthn
    options are returned to the agent; the user signs in the browser.

Quick-start (agent mode):
    export FORTSIGNAL_API_KEY="fs_key_..."
    export FORTSIGNAL_AGENT_ID="my-agent"
    export FORTSIGNAL_AGENT_KEY="/path/to/key.json"
    fortsignal-deepagents

Or use the helper:
    from fortsignal_deepagents import create_fortsignal_deep_agent

    agent = create_fortsignal_deep_agent(
        model="openai:gpt-4o",
        agent_id="my-agent",
        agent_key_path="/path/to/key.json",
    )
"""

from fortsignal_deepagents.middleware import FortSignalMiddleware, RISKY_TOOLS, _PendingChallenge

__all__ = [
    "FortSignalMiddleware",
    "RISKY_TOOLS",
    "_PendingChallenge",
    "create_fortsignal_deep_agent",
]

__version__ = "0.1.0"


def create_fortsignal_deep_agent(
    model: str | None = None,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    user_id: str | None = None,
    agent_id: str | None = None,
    agent_key_path: str | None = None,
    **kwargs,
):
    """Create a Deep Agent protected by FortSignal middleware.

    This is a convenience wrapper around ``create_deep_agent()`` that
    automatically injects ``FortSignalMiddleware`` into the middleware
    stack.

    Args:
        model: Model specifier (e.g. ``"openai:gpt-4o"``).
        api_key: FortSignal API key (default: ``$FORTSIGNAL_API_KEY``).
        base_url: FortSignal API base URL (default: ``$FORTSIGNAL_BASE_URL``).
        user_id: FortSignal user ID for passkey mode.
        agent_id: FortSignal agent ID for autonomous mode.
        agent_key_path: Path to Ed25519 agent key JSON file.
        **kwargs: Forwarded to ``create_deep_agent()``.

    Returns:
        A compiled agent graph with FortSignal security applied.
    """
    from deepagents import create_deep_agent as _create_deep_agent

    middleware = kwargs.pop("middleware", [])
    fortsignal = FortSignalMiddleware(
        user_id=user_id, agent_id=agent_id, agent_key_path=agent_key_path,
        api_key=api_key, base_url=base_url,
    )
    secured_middleware = [fortsignal, *list(middleware)]

    return _create_deep_agent(model=model, middleware=secured_middleware, **kwargs)
