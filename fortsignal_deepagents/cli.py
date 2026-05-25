"""CLI entry point for FortSignal-secured Deep Agents.

Usage:
    export FORTSIGNAL_API_KEY=fs_key_...
    fortsignal-deepagents [--model MODEL] [--message MSG]

This wraps ``deepagents-code`` and injects ``FortSignalMiddleware`` into
both the parent process (direct agent creation) and the child LangGraph
server subprocess (interactive TUI).
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings

# Suppress noisy deprecation warnings from langchain_core
warnings.filterwarnings("ignore", module="langchain_core._api.deprecation")


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


def _inject_hook_into_server_graph(work_dir: str, **mw_kwargs: str | None) -> None:
    """Inject middleware into the subprocess's server_graph.py.

    Patches ``create_deep_agent`` *before* ``make_graph()`` runs by inserting
    code right after the imports block.
    """
    sg_path = os.path.join(work_dir, "server_graph.py")
    if not os.path.isfile(sg_path):
        return

    uid = mw_kwargs.get("user_id")
    aid = mw_kwargs.get("agent_id")
    akp = mw_kwargs.get("agent_key_path")
    apk = mw_kwargs.get("api_key")
    bur = mw_kwargs.get("base_url")

    injection = f"""
# --- FortSignal middleware injection ---
import os as _fs_os
if _fs_os.environ.get("FORTSIGNAL_API_KEY"):
    import deepagents.graph as _fs_g
    import deepagents as _fs_da
    from fortsignal_deepagents import FortSignalMiddleware
    _fs_o_g = _fs_g.create_deep_agent
    _fs_o_da = _fs_da.create_deep_agent
    def _fs_secured(*_a, **_kw):
        mw = list(_kw.pop("middleware", ()))
        mw.insert(0, FortSignalMiddleware(
            user_id={uid!r}, agent_id={aid!r},
            agent_key_path={akp!r}, api_key={apk!r},
            base_url={bur!r},
            source=_fs_os.environ.get("FORTSIGNAL_SOURCE") or None,
        ))
        return _fs_o_g(*_a, middleware=mw, **_kw)
    _fs_g.create_deep_agent = _fs_secured
    _fs_da.create_deep_agent = _fs_secured
# --- end FortSignal injection ---
"""

    with open(sg_path) as f:
        content = f.read()

    # Insert right after the imports, before any function definitions
    marker = "\nlogger = logging.getLogger(__name__)\n"
    if marker in content:
        content = content.replace(marker, injection + marker, 1)
        with open(sg_path, "w") as f:
            f.write(content)


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

    # ── Inject FortSignalMiddleware ──────────────────────────────────────
    # The server spawns a child subprocess (langgraph dev) that imports
    # fresh, so parent-process monkey-patches don't reach it.  We patch
    # both paths:
    #
    #   1. Parent process: replace create_deep_agent at both module levels.
    #   2. Child subprocess: hook _scaffold_workspace to insert injection
    #      code into the server_graph.py that gets copied to the work dir.
    if api_key:
        from fortsignal_deepagents import FortSignalMiddleware

        # ── Parent process ───────────────────────────────────────────────
        import deepagents.graph as _graph_mod
        import deepagents as _deepagents_mod

        _orig_graph = _graph_mod.create_deep_agent
        _orig_deepagents = _deepagents_mod.create_deep_agent
        _fs_source = os.getenv("FORTSIGNAL_SOURCE", "")

        def _secured_create(*pa, **kw):
            mw = list(kw.pop("middleware", ()))
            mw.insert(0, FortSignalMiddleware(
                user_id=user_id, agent_id=agent_id, agent_key_path=agent_key,
                api_key=api_key, base_url=base_url,
                source=_fs_source or None,
            ))
            return _orig_graph(*pa, middleware=mw, **kw)

        _graph_mod.create_deep_agent = _secured_create
        _deepagents_mod.create_deep_agent = _secured_create

        # ── Child subprocess ─────────────────────────────────────────────
        import deepagents_code.server_manager as _sm

        _orig_scaffold = _sm._scaffold_workspace

        def _patched_scaffold(work_dir):
            _orig_scaffold(work_dir)
            _inject_hook_into_server_graph(
                work_dir,
                user_id=user_id, agent_id=agent_id,
                agent_key_path=agent_key, api_key=api_key,
                base_url=base_url,
            )

        _sm._scaffold_workspace = _patched_scaffold

    # ── Delegate to deepagents-code CLI ──────────────────────────────────
    try:
        from deepagents_code.main import cli_main as deepagents_main
    except ImportError:
        msg = (
            "The deepagents-code package is required. Install it with:\n"
            "    pip install deepagents-code\n"
        )
        print(msg, file=sys.stderr)
        sys.exit(1)

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
    forwarded.extend(remaining_args)

    sys.argv = [sys.argv[0], *forwarded]
    deepagents_main()
    # unreachable — deepagents_main calls sys.exit()


if __name__ == "__main__":
    main()
