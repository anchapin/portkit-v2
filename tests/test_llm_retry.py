"""Transient provider failures are retried; the retry is invisible to transcripts (#137).

From Alex's spot-check: an OpenRouter HTTP 504 (provider Google) ended a group as
an error with nothing retried, and an empty reply with finish_reason=error and
175 billed output tokens ended another.
"""
import io
import socket
import urllib.error

import pytest

from portkit.agent import http
from portkit.agent.anthropic import AnthropicClient
from portkit.agent.budget import Usage
from portkit.agent.gemini import GeminiClient
from portkit.agent.http import LLMError, RetryPolicy
from portkit.agent.loop import Message
from portkit.agent.openai import OpenAIClient
from portkit.agent.transcript import RecordingClient, ReplayClient, load, request_digest

OK_OPENAI = {
    "choices": [{"finish_reason": "stop", "message": {"content": "done"}}],
    "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
}
EMPTY_ERROR = {
    "choices": [{"finish_reason": "error", "message": {"content": None}}],
    "usage": {"prompt_tokens": 100, "completion_tokens": 175, "total_tokens": 275},
}
OK_ANTHROPIC = {"content": [{"type": "text", "text": "done"}], "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": 1}}
OK_GEMINI = {"candidates": [{"content": {"role": "model", "parts": [{"text": "done"}]}, "finishReason": "STOP"}],
             "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 1}}


class Script:
    """A fake transport: each entry is a reply dict or an exception to raise."""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.bodies = []

    def __call__(self, url, headers, body):
        self.bodies.append(body)
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step


class Sleeps(list):
    def __call__(self, seconds):
        self.append(seconds)


def _policy(retries=2):
    sleeps = Sleeps()
    return RetryPolicy(max_retries=retries, sleep=sleeps), sleeps


USER = [Message("user", "x")]


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_retryable_statuses_are_retried(status):
    policy, sleeps = _policy()
    transport = Script(LLMError("busy", status=status), OK_OPENAI)
    msg = OpenAIClient("m", transport=transport, retry=policy).complete(USER, [])
    assert msg.content == "done" and len(transport.bodies) == 2 and sleeps == [1.0]
    assert transport.bodies[0] == transport.bodies[1]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_client_errors_are_not_retried(status):
    policy, sleeps = _policy()
    transport = Script(LLMError("no", status=status), OK_OPENAI)
    with pytest.raises(LLMError):
        OpenAIClient("m", transport=transport, retry=policy).complete(USER, [])
    assert len(transport.bodies) == 1 and sleeps == []


def test_retries_are_bounded_with_exponential_backoff():
    policy, sleeps = _policy(retries=2)
    transport = Script(*(LLMError("504", status=504) for _ in range(3)), OK_OPENAI)
    with pytest.raises(LLMError, match="504"):
        OpenAIClient("m", transport=transport, retry=policy).complete(USER, [])
    assert len(transport.bodies) == 3 and sleeps == [1.0, 2.0]


def test_retry_after_is_honoured_and_capped():
    policy, sleeps = _policy()
    transport = Script(LLMError("slow", status=429, retry_after=7), LLMError("slow", status=429, retry_after=900), OK_OPENAI)
    OpenAIClient("m", transport=transport, retry=policy).complete(USER, [])
    assert sleeps == [7, http.MAX_RETRY_AFTER]


def test_timeouts_and_connection_failures_are_retried():
    policy, sleeps = _policy()
    transport = Script(LLMError("timed out", transient=True), LLMError("could not reach", transient=True), OK_OPENAI)
    assert OpenAIClient("m", transport=transport, retry=policy).complete(USER, []).content == "done"
    assert len(sleeps) == 2


def test_a_200_with_an_openrouter_error_body_is_retried():
    policy, _ = _policy()
    transport = Script({"error": {"code": 502, "message": "Provider returned error"}}, OK_OPENAI)
    assert OpenAIClient("m", transport=transport, retry=policy).complete(USER, []).content == "done"
    # A non-retryable code in the body is still an error, at once.
    transport = Script({"error": {"code": 400, "message": "bad"}}, OK_OPENAI)
    with pytest.raises(LLMError, match="provider error"):
        OpenAIClient("m", transport=transport, retry=policy).complete(USER, [])


def test_env_zero_turns_retries_off(monkeypatch):
    monkeypatch.setenv("PORTKIT_LLM_MAX_RETRIES", "0")
    transport = Script(LLMError("504", status=504), OK_OPENAI)
    with pytest.raises(LLMError):
        OpenAIClient("m", transport=transport).complete(USER, [])
    transport = Script(EMPTY_ERROR, OK_OPENAI)
    assert OpenAIClient("m", transport=transport).complete(USER, []).finish_reason == "error"


def test_env_default_and_bad_values():
    assert RetryPolicy.from_env({}).max_retries == 2
    assert RetryPolicy.from_env({"PORTKIT_LLM_MAX_RETRIES": "5"}).max_retries == 5
    with pytest.raises(ValueError):
        RetryPolicy.from_env({"PORTKIT_LLM_MAX_RETRIES": "lots"})
    with pytest.raises(ValueError):
        RetryPolicy.from_env({"PORTKIT_LLM_MAX_RETRIES": "-1"})


def test_an_empty_error_reply_is_retried_once_and_its_tokens_counted():
    policy, _ = _policy()
    transport = Script(EMPTY_ERROR, OK_OPENAI)
    msg = OpenAIClient("m", transport=transport, retry=policy).complete(USER, [])
    assert msg.content == "done" and len(transport.bodies) == 2
    # The discarded reply's billed tokens ride on the final reply.
    assert msg.usage == Usage(200, 185)


def test_a_second_empty_error_reply_is_returned():
    policy, _ = _policy()
    transport = Script(EMPTY_ERROR, EMPTY_ERROR, OK_OPENAI)
    msg = OpenAIClient("m", transport=transport, retry=policy).complete(USER, [])
    assert msg.finish_reason == "error" and len(transport.bodies) == 2
    assert msg.usage == Usage(200, 350)


def test_other_empty_replies_are_not_retried():
    policy, _ = _policy()
    length = {"choices": [{"finish_reason": "length", "message": {"content": None}}]}
    transport = Script(length, OK_OPENAI)
    assert OpenAIClient("m", transport=transport, retry=policy).complete(USER, []).finish_reason == "length"
    assert len(transport.bodies) == 1


def test_anthropic_and_gemini_native_retry_too():
    policy, _ = _policy()
    transport = Script(LLMError("overloaded", status=503), OK_ANTHROPIC)
    assert AnthropicClient("m", transport=transport, retry=policy).complete(USER, []).content == "done"
    transport = Script(LLMError("unavailable", status=503), OK_GEMINI)
    assert GeminiClient("m", transport=transport, retry=policy).complete(USER, []).content == "done"


def test_a_retried_request_records_one_line_and_replays(tmp_path):
    policy, _ = _policy()
    transport = Script(LLMError("504", status=504), EMPTY_ERROR, OK_OPENAI)
    path = tmp_path / "t.jsonl"
    recorder = RecordingClient(OpenAIClient("m", transport=transport, retry=policy), path)
    msg = recorder.complete([Message("system", "s"), *USER], [])
    entries = load(path)
    assert len(entries) == 1
    assert entries[0]["request"] == request_digest([Message("system", "s"), *USER], [])
    assert entries[0]["reply"]["content"] == "done"
    assert entries[0]["reply"]["usage"] == {"input_tokens": 200, "output_tokens": 185}
    replayed = ReplayClient(path).complete([Message("system", "s"), *USER], [])
    assert replayed == msg


def test_post_json_marks_timeouts_and_reads_retry_after(monkeypatch):
    def timeout(request, timeout):
        raise socket.timeout("timed out")

    monkeypatch.setattr(http.urllib.request, "urlopen", timeout)
    with pytest.raises(LLMError) as info:
        http.post_json("http://x/y", {}, {})
    assert info.value.transient and info.value.retryable

    def refused(request, timeout):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(http.urllib.request, "urlopen", refused)
    with pytest.raises(LLMError) as info:
        http.post_json("http://x/y", {}, {})
    assert info.value.retryable

    def busy(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many", {"Retry-After": "3"}, io.BytesIO(b"{}"))

    monkeypatch.setattr(http.urllib.request, "urlopen", busy)
    with pytest.raises(LLMError) as info:
        http.post_json("http://x/y", {}, {})
    assert info.value.status == 429 and info.value.retry_after == 3.0 and info.value.retryable
