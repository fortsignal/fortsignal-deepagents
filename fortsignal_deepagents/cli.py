"""CLI entry point for FortSignal-secured Deep Agents.

Usage:
    export FORTSIGNAL_API_KEY=fs_key_...
    fortsignal-deepagents [--model MODEL] [--message MSG]

This is a thin wrapper around the standard ``deepagents`` CLI. It patches
``create_deep_agent`` to inject ``FortSignalMiddleware`` before handing
control to the real CLI loop.
"""

import argparse
import os
import sys
import warnings

# Suppress noisy deprecation warnings from langchain_core
warnings.filterwarnings("ignore", module="langchain_core._api.deprecation")

DEEPAGENTS_ENTRY = "deepagents"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fortsignal-deepagents",
        description="FortSignal-secured Deep Agent — cryptographically safe coding agent",
    )
    parser.add_argument(
        "--model", "-M",
        default=os.getenv("FORTSIGNAL_MODEL"),
        help="Model to use (default: $FORTSIGNAL_MODEL)",
    )
    parser.add_argument(
        "--message", "-m",
        default=None,
        help="Initial prompt to auto-submit on start",
    )
    parser.add_argument(
        "--user-id",
        default=None,
        help="FortSignal user ID for passkey mode (default: $FORTSIGNAL_USER_ID)",
    )
    parser.add_argument(
        "--agent-id",
        default=None,
        help="FortSignal agent ID for autonomous mode (default: $FORTSIGNAL_AGENT_ID)",
    )
    parser.add_argument(
        "--agent-key",
        default=None,
        help="Path to Ed25519 agent key JSON file (default: $FORTSIGNAL_AGENT_KEY)",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="FortSignal API key (default: $FORTSIGNAL_API_KEY)",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="FortSignal API base URL (default: $FORTSIGNAL_BASE_URL or https://api.fortsignal.com)",
    )
    parser.add_argument(
        "--agent", "-a",
        default=None,
        help="Deep Agent profile to use (e.g., coder, researcher)",
    )
    parser.add_argument(
        "--skill",
        default=None,
        help="Invoke a skill when the session starts",
    )
    parser.add_argument(
        "--startup-cmd",
        default=None,
        help="Shell command to run at startup, before first prompt",
    )
    return parser


def main() -> None:
    """Main entry point for the FortSignal Deep Agents CLI."""

    parser = _build_parser()
    args, remaining_args = parser.parse_known_args()

    api_key = args.api_key or os.getenv("FORTSIGNAL_API_KEY")
    user_id = args.user_id or os.getenv("FORTSIGNAL_USER_ID")
    agent_id = args.agent_id or os.getenv("FORTSIGNAL_AGENT_ID")
    agent_key = args.agent_key or os.getenv("FORTSIGNAL_AGENT_KEY")
    if not api_key:
        print(
            "⚠️  FORTSIGNAL_API_KEY is not set.\n"
            "   Risky tools (write_file, edit_file, execute, task) will be blocked.\n"
            "   Set the env var or pass --api-key to enable FortSignal security.\n",
            file=sys.stderr,
        )

    base_url = args.base_url or os.getenv("FORTSIGNAL_BASE_URL")

    # ── Patch create_deep_agent before deepagents CLI loads ──────────────
    from fortsignal_deepagents import FortSignalMiddleware

    # We monkey-patch at the deepagents module level so the CLI's own
    # imports of create_deep_agent pick up our secured version.
    import deepagents.graph as _graph_mod

    _orig_create = _graph_mod.create_deep_agent

    def _secured_create(*p_args, **p_kwargs):
        middleware = list(p_kwargs.pop("middleware", ()))
        middleware.insert(0, FortSignalMiddleware(
            user_id=user_id, agent_id=agent_id, agent_key_path=agent_key,
            api_key=api_key, base_url=base_url,
        ))
        return _orig_create(*p_args, middleware=middleware, **p_kwargs)

    _graph_mod.create_deep_agent = _secured_create

    # ── Delegate to deepagents CLI ───────────────────────────────────────
    # The deepagents CLI uses runpy or direct invocation. We simply import
    # and run its main function.
    try:
        from deepagents_cli.main import cli_main as deepagents_main  # type: ignore[import-untyped]
    except ImportError:
        # Fallback: try running via python -m
        msg = (
            "The deepagents CLI package is required. Install it with:\n"
            "    uv tool install deepagents-cli\n"
            "or:\n"
            "    pip install deepagents-cli\n"
        )
        print(msg, file=sys.stderr)
        sys.exit(1)

    # Build forwarded args — pass through model, message, user-id, agent-id,
    # agent-key, agent, skill, startup-cmd if explicitly provided
    forwarded = []
    for fflag, fval in (
        ("--model", args.model),
        ("--message", args.message),
        ("--user-id", args.user_id),
        ("--agent-id", args.agent_id),
        ("--agent-key", args.agent_key),
        ("--agent", args.agent),
        ("--skill", args.skill),
        ("--startup-cmd", args.startup_cmd),
    ):
        if fval is not None:
            forwarded.append(fflag)
            forwarded.append(fval)

    sys.argv = [sys.argv[0], *forwarded, *remaining_args]
    sys.exit(deepagents_main())


if __name__ == "__main__":
    main()
