from pathlib import Path

import pytest

from app import main


def test_process_local_state_rejects_multi_worker_environment(monkeypatch):
    monkeypatch.setenv('WEB_CONCURRENCY', '2')
    with pytest.raises(RuntimeError, match='must be 1'):
        main._enforce_single_worker_config()


def test_docker_contract_uses_one_worker_no_access_log_and_real_render_health(project_root: Path):
    dockerfile = (project_root / 'Dockerfile').read_text()
    # Railway assigns PORT dynamically. The shell wrapper is intentional so
    # the container does not listen on a hard-coded, unroutable port.
    assert '${PORT:-8000}' in dockerfile
    assert '--workers 1' in dockerfile
    assert '--no-access-log' in dockerfile
    # Production must use the same LibreOffice 24.2 renderer family exercised
    # by the Linux release gate; Bookworm's 7.4 renderer changed demo layout.
    assert 'FROM ubuntu:24.04' in dockerfile
    assert '/health/deep-readiness' in dockerfile


def test_blank_session_root_uses_dedicated_temp_default():
    resolved = main._resolve_session_root('')
    assert resolved.name == 'venue-agent-sessions'
    assert resolved.is_absolute()


def test_relative_or_dangerous_session_roots_are_rejected():
    with pytest.raises(RuntimeError):
        main._resolve_session_root('relative/path')
    with pytest.raises(RuntimeError):
        main._resolve_session_root('/')


def test_railway_config_uses_deep_readiness_and_dockerfile(project_root: Path):
    import json
    raw = json.loads((project_root / "railway.json").read_text(encoding="utf-8"))
    assert raw["build"]["builder"] == "DOCKERFILE"
    assert raw["build"]["dockerfilePath"] == "Dockerfile"
    assert raw["deploy"]["healthcheckPath"] == "/health/deep-readiness"
    assert raw["deploy"]["healthcheckTimeout"] >= 120
    assert raw["deploy"]["restartPolicyType"] == "ON_FAILURE"


def test_deployment_runbook_requires_one_replica_and_live_full_check(project_root: Path):
    text = (project_root / "docs/DEPLOYMENT_RUNBOOK.md").read_text(encoding="utf-8")
    assert "one Railway replica" in text
    assert "--require-gemini" in text
    assert "--full" in text
    assert "downloaded output bytes exactly match" in text
