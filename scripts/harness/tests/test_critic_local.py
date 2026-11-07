# SPDX-License-Identifier: AGPL-3.0-or-later
"""The cross-family sample comes from a local model behind an OpenAI-compatible endpoint."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import critic
import pytest
from conftest import HarnessRepo, clean


class FakeOpenAI:
    """A tiny /v1 server: GET /models, POST /chat/completions."""

    def __init__(self) -> None:
        self.reply: str = json.dumps(clean())
        self.reject_json_mode = False
        self.requests: list[dict[str, Any]] = []
        self.headers: list[dict[str, str]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                pass

            def _send(self, code: int, body: dict[str, Any]) -> None:
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:
                self._send(200, {"data": [{"id": "qwen3.8-27b"}, {"id": "other"}]})

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(body)
                fake.headers.append(dict(self.headers))
                if fake.reject_json_mode and "response_format" in body:
                    self._send(400, {"error": "response_format not supported"})
                    return
                self._send(200, {"choices": [{"message": {"content": fake.reply}}]})

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()


@pytest.fixture
def openai() -> Iterator[FakeOpenAI]:
    server = FakeOpenAI()
    yield server
    server.close()


def test_diff_lines_get_their_new_side_numbers() -> None:
    diff = (
        "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -10,3 +10,4 @@ def f():\n"
        " keep\n-old\n+new\n+added\n tail"
    )
    out = critic.annotate_diff(diff).splitlines()
    assert out[4] == "   10  keep"
    assert out[5] == "      -old"
    assert out[6] == "   11 +new"
    assert out[7] == "   12 +added"
    assert out[8] == "   13  tail"


def test_prompt_carries_plan_and_diff_and_flags_truncation() -> None:
    qs = [critic.Question("Q-SCOPE", "scope?")]
    prompt, cut = critic.render_local_prompt("abc", "p", "PLAN TEXT", qs, "+x\n" * 10, 1000)
    assert "PLAN TEXT" in prompt
    assert "Q-SCOPE: scope?" in prompt
    assert not cut
    prompt, cut = critic.render_local_prompt("abc", "p", "PLAN", qs, "+line\n" * 500, 200)
    assert cut
    assert "[TRUNCATED]" in prompt
    assert 'answer "na" for anything you could not see' in prompt


def test_local_sample_picks_the_model_and_sends_the_key(
    openai: FakeOpenAI, tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude/state").mkdir(parents=True)
    openai.reply = "<think>let me look</think>\n" + json.dumps(clean(Q_SCOPE="na"))
    s = critic.local_sample("prompt", openai.url, "", "sk-unsloth-test", 30)
    assert s.ok, s.error
    assert s.reviewer == "local:qwen3.8-27b"
    assert openai.requests[0]["model"] == "qwen3.8-27b"
    assert openai.requests[0]["response_format"] == {"type": "json_object"}
    assert openai.headers[0]["Authorization"] == "Bearer sk-unsloth-test"
    assert any(a["id"] == "Q-SCOPE" and a["answer"] == "na" for a in s.answers)


def test_server_without_json_mode_is_asked_again_without_it(
    openai: FakeOpenAI, tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude/state").mkdir(parents=True)
    openai.reject_json_mode = True
    s = critic.local_sample("prompt", openai.url, "gemma4:31b", "", 30)
    assert s.ok, s.error
    assert len(openai.requests) == 2
    assert "response_format" not in openai.requests[1]


def test_unreachable_or_unparsable_local_model_is_not_ok(
    openai: FakeOpenAI, tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude/state").mkdir(parents=True)
    down = critic.local_sample("p", "http://127.0.0.1:9/v1", "m", "", 2)
    assert not down.ok
    assert "unavailable" in down.error
    openai.reply = "I think the change is fine."
    prose = critic.local_sample("p", openai.url, "m", "", 30)
    assert not prose.ok
    assert "could not be parsed" in prose.error


def test_end_to_end_local_sample_is_the_cross_family_witness(
    repo: HarnessRepo, openai: FakeOpenAI
) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\nY = 3\n")
    repo.commit("work")
    bindir = repo.root.parent / "bin"
    bindir.mkdir(exist_ok=True)
    payload = {"structured_output": clean(), "total_cost_usd": 0.02, "num_turns": 4}
    claude = bindir / "claude"
    claude.write_text(f"#!/usr/bin/env bash\necho '{json.dumps(payload)}'\n")
    claude.chmod(0o755)
    # the local model flags line 2, which the annotated diff showed it
    openai.reply = json.dumps(clean(Q_SCOPE=("yes", "src/app.py", 2)))
    out = repo.run(
        "scripts/review_gate.sh",
        env={
            "PATH": f"{bindir}:/usr/bin:/bin",
            "KALETA_CROSS_REVIEW": "1",
            "KALETA_CROSS_REVIEW_URL": openai.url,
        },
    )
    assert out.returncode == 0, out.stderr
    c = json.loads(repo.state("critic.json") or "{}")
    assert c["cross_family_present"] is True
    assert [s["reviewer"] for s in c["samples"]] == ["claude", "claude", "local:qwen3.8-27b"]
    scope = next(q for q in c["questions"] if q["id"] == "Q-SCOPE")
    assert (scope["violations"], scope["k_valid"]) == (1, 3)
    prompt = openai.requests[0]["messages"][0]["content"]
    assert "    2 +Y = 3" in prompt  # the annotated diff
    assert "Fixture plan" in prompt  # the plan itself


def test_local_model_down_makes_a_required_cross_sample_an_error(repo: HarnessRepo) -> None:
    repo.new_plan()
    repo.write("src/app.py", "X = 2\n")
    repo.commit("work")
    bindir = repo.root.parent / "bin"
    bindir.mkdir(exist_ok=True)
    payload = {"structured_output": clean(), "total_cost_usd": 0.02, "num_turns": 4}
    (bindir / "claude").write_text(f"#!/usr/bin/env bash\necho '{json.dumps(payload)}'\n")
    (bindir / "claude").chmod(0o755)
    out = repo.run(
        "scripts/review_gate.sh",
        env={
            "PATH": f"{bindir}:/usr/bin:/bin",
            "KALETA_CROSS_REVIEW": "1",
            "KALETA_CROSS_REVIEW_URL": "http://127.0.0.1:9/v1",
            "KALETA_CROSS_REVIEW_TIMEOUT": "2",
        },
    )
    assert out.returncode == 1
    c = json.loads(repo.state("critic.json") or "{}")
    assert c["error_kind"] == "cross_unavailable"
    assert "unavailable" in c["error"]
