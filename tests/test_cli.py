"""Tests for the FortSignal Deep Agents CLI entry point."""

from __future__ import annotations

from pytest import MonkeyPatch

from fortsignal_deepagents.cli import _build_parser


class TestCLIArgs:
    def test_base_url_default(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.base_url is None

    def test_user_id_from_env(self, monkeypatch: MonkeyPatch):
        parser = _build_parser()
        monkeypatch.setenv("FORTSIGNAL_USER_ID", "user_env")
        args = parser.parse_args([])
        assert args.user_id is None  # env resolved in main(), not argparse

    def test_agent_id_from_env(self, monkeypatch: MonkeyPatch):
        parser = _build_parser()
        monkeypatch.setenv("FORTSIGNAL_AGENT_ID", "my-agent")
        args = parser.parse_args([])
        assert args.agent_id is None  # env resolved in main()

    def test_agent_key_from_env(self, monkeypatch: MonkeyPatch):
        parser = _build_parser()
        monkeypatch.setenv("FORTSIGNAL_AGENT_KEY", "/path/to/key.json")
        args = parser.parse_args([])
        assert args.agent_key is None  # env resolved in main()

    def test_api_key_from_env(self, monkeypatch: MonkeyPatch):
        parser = _build_parser()
        monkeypatch.setenv("FORTSIGNAL_API_KEY", "fs_key_env")
        args = parser.parse_args([])
        assert args.api_key is None

    def test_override_env_with_flag(self, monkeypatch: MonkeyPatch):
        parser = _build_parser()
        monkeypatch.setenv("FORTSIGNAL_API_KEY", "fs_key_env")
        args = parser.parse_args(["--api-key", "fs_key_explicit"])
        assert args.api_key == "fs_key_explicit"
