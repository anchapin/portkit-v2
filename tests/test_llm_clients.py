"""Provider clients, tested with a recorded HTTP layer: no API key, no network."""
import io
import json
import urllib.error
from pathlib import Path

import pytest

from portkit.agent import http
from portkit.agent.anthropic import AnthropicClient, to_anthropic_messages
from portkit.agent.factory import make_client
from portkit.agent.fake import FakeLLM
from portkit.agent.http import LLMError
from portkit.agent.loop import AgentSession, LLMClient, Message, ToolCall
from portkit.agent.openai import OpenAIClient, to_openai_message
from portkit.agent.tools import SYSTEM_PROMPT, ToolBox

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fixtures" / "residue_mod" / "input"
RECIPE = "data/examplemod/recipes/steel_block.json"


class Recorder:
    """A transport that records requests and replays canned provider replies."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, url, headers, body):
        self.requests.append({"url": url, "headers": headers, "body": json.loads(json.dumps(body))})
        return self.replies.pop(0)


# -- canned replies in each provider's wire format ----------------------------
def oa_call(call_id, name, **args):
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
    ]}}]}


def oa_text(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def an_call(call_id, name, **args):
    return {"content": [{"type": "tool_use", "id": call_id, "name": name, "input": args}], "stop_reason": "tool_use"}


def an_text(text):
    return {"content": [{"type": "text", "text": text}], "stop_reason": "end_turn"}


SCRIPTS = {
    "openai": [oa_call("c1", "list_source"), oa_call("c2", "read_source", path=RECIPE), oa_text("done")],
    "anthropic": [an_call("c1", "list_source"), an_call("c2", "read_source", path=RECIPE), an_text("done")],
}


# -- the acceptance criterion -------------------------------------------------
@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_same_session_runs_against_either_provider(tmp_path, provider):
    transport = Recorder(SCRIPTS[provider])
    client = make_client(provider, "some-model", env={}, transport=transport)
    result = AgentSession(client, ToolBox(SOURCE, tmp_path), SYSTEM_PROMPT).run("Convert the residue.")

    assert result.stopped == "done" and result.steps == 3
    assert result.messages[-1].content == "done"
    tool_outputs = [m for m in result.messages if m.role == "tool"]
    assert [m.tool_call_id for m in tool_outputs] == ["c1", "c2"]
    assert "steel_block" in tool_outputs[1].content
    assert len(transport.requests) == 3


def test_every_client_satisfies_the_protocol():
    for client in (FakeLLM([]), OpenAIClient("m"), AnthropicClient("m")):
        assert isinstance(client, LLMClient)


# -- OpenAI-style translation -------------------------------------------------
def test_openai_request_shape():
    transport = Recorder([oa_text("hi")])
    tools = [{"name": "validate", "description": "check", "parameters": {"type": "object", "properties": {}}}]
    msgs = [
        Message("system", "sys"),
        Message("user", "go"),
        Message("assistant", tool_calls=[ToolCall("c1", "read_source", {"path": "a.json"})]),
        Message("tool", '{"ok": true}', tool_call_id="c1"),
    ]
    OpenAIClient("gpt-x", api_key="k", base_url="http://local/v1/", transport=transport,
                 extra={"temperature": 0}).complete(msgs, tools)
    req = transport.requests[0]
    assert req["url"] == "http://local/v1/chat/completions"
    assert req["headers"]["authorization"] == "Bearer k"
    body = req["body"]
    assert body["model"] == "gpt-x" and body["temperature"] == 0
    assert body["tools"] == [{"type": "function", "function": tools[0]}]
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    call = body["messages"][2]["tool_calls"][0]
    assert call["id"] == "c1" and json.loads(call["function"]["arguments"]) == {"path": "a.json"}
    assert body["messages"][3] == {"role": "tool", "tool_call_id": "c1", "content": '{"ok": true}'}


def test_openai_omits_tools_and_auth_when_absent():
    transport = Recorder([oa_text("hi")])
    reply = OpenAIClient("m", transport=transport).complete([Message("user", "x")], [])
    assert reply == Message("assistant", "hi")
    assert "tools" not in transport.requests[0]["body"]
    assert "authorization" not in transport.requests[0]["headers"]


def test_openai_parses_multiple_and_malformed_tool_calls():
    reply = {"choices": [{"message": {"content": "thinking", "tool_calls": [
        {"id": "a", "type": "function", "function": {"name": "validate", "arguments": ""}},
        {"id": "b", "type": "function", "function": {"name": "read_source", "arguments": "{not json"}},
    ]}}]}
    msg = OpenAIClient("m", transport=Recorder([reply])).complete([Message("user", "x")], [])
    assert msg.content == "thinking"
    assert msg.tool_calls[0] == ToolCall("a", "validate", {})
    assert msg.tool_calls[1].arguments == {"_invalid_arguments": "{not json"}


def test_openai_malformed_arguments_become_tool_error_not_crash(tmp_path):
    bad = {"choices": [{"message": {"tool_calls": [
        {"id": "a", "type": "function", "function": {"name": "read_source", "arguments": "{oops"}}]}}]}
    client = OpenAIClient("m", transport=Recorder([bad, oa_text("sorry")]))
    result = AgentSession(client, ToolBox(SOURCE, tmp_path), SYSTEM_PROMPT).run("go")
    assert result.stopped == "done"
    assert "error" in result.messages[-2].content


def test_openai_unexpected_reply_raises():
    with pytest.raises(LLMError):
        OpenAIClient("m", transport=Recorder([{"error": {"message": "nope"}}])).complete([], [])


def test_openai_message_round_trip_of_plain_text():
    assert to_openai_message(Message("assistant", "ok")) == {"role": "assistant", "content": "ok"}


# -- Anthropic-style translation ----------------------------------------------
def test_anthropic_request_shape():
    transport = Recorder([an_text("hi")])
    tools = [{"name": "read_source", "description": "read", "parameters": {"type": "object"}}]
    AnthropicClient("claude-x", api_key="k", max_tokens=99, transport=transport).complete(
        [Message("system", "sys"), Message("user", "go")], tools
    )
    req = transport.requests[0]
    assert req["url"] == "https://api.anthropic.com/v1/messages"
    assert req["headers"]["x-api-key"] == "k"
    assert req["headers"]["anthropic-version"] == "2023-06-01"
    body = req["body"]
    assert body["system"] == "sys" and body["max_tokens"] == 99 and body["model"] == "claude-x"
    assert body["tools"] == [{"name": "read_source", "description": "read", "input_schema": {"type": "object"}}]
    assert body["messages"] == [{"role": "user", "content": [{"type": "text", "text": "go"}]}]


def test_anthropic_groups_tool_results_into_one_user_turn():
    system, turns = to_anthropic_messages([
        Message("system", "sys"),
        Message("user", "go"),
        Message("assistant", "two calls", tool_calls=[ToolCall("a", "x", {}), ToolCall("b", "y", {"k": 1})]),
        Message("tool", "ra", tool_call_id="a"),
        Message("tool", "rb", tool_call_id="b"),
    ])
    assert system == "sys"
    assert [t["role"] for t in turns] == ["user", "assistant", "user"]
    assert turns[1]["content"] == [
        {"type": "text", "text": "two calls"},
        {"type": "tool_use", "id": "a", "name": "x", "input": {}},
        {"type": "tool_use", "id": "b", "name": "y", "input": {"k": 1}},
    ]
    assert turns[2]["content"] == [
        {"type": "tool_result", "tool_use_id": "a", "content": "ra"},
        {"type": "tool_result", "tool_use_id": "b", "content": "rb"},
    ]


def test_anthropic_parses_text_and_tool_use_together():
    reply = {"content": [
        {"type": "text", "text": "let me look"},
        {"type": "tool_use", "id": "t1", "name": "list_source", "input": {}},
    ]}
    msg = AnthropicClient("m", transport=Recorder([reply])).complete([Message("user", "x")], [])
    assert msg.content == "let me look"
    assert msg.tool_calls == [ToolCall("t1", "list_source", {})]


def test_anthropic_unexpected_reply_raises():
    with pytest.raises(LLMError):
        AnthropicClient("m", transport=Recorder([{"type": "error"}])).complete([Message("user", "x")], [])


# -- factory --------------------------------------------------------------------
def test_factory_reads_env():
    env = {"PORTKIT_LLM_PROVIDER": "Anthropic", "PORTKIT_LLM_MODEL": "claude-y", "ANTHROPIC_API_KEY": "sk"}
    client = make_client(env=env)
    assert isinstance(client, AnthropicClient)
    assert client.model == "claude-y" and client.api_key == "sk"


def test_factory_config_beats_env_and_args_beat_config():
    env = {"PORTKIT_LLM_PROVIDER": "anthropic", "PORTKIT_LLM_MODEL": "env-model", "MY_KEY": "mk"}
    config = {"provider": "openai", "model": "cfg-model", "base_url": "http://gw/v1", "api_key_env": "MY_KEY"}
    client = make_client(config=config, env=env)
    assert isinstance(client, OpenAIClient)
    assert (client.model, client.base_url, client.api_key) == ("cfg-model", "http://gw/v1", "mk")
    assert make_client("openai", "arg-model", config=config, env=env).model == "arg-model"


def test_factory_rejects_missing_or_unknown_provider_and_model():
    with pytest.raises(ValueError, match="provider"):
        make_client(env={})
    with pytest.raises(ValueError, match="provider"):
        make_client("cohere", "m", env={})
    with pytest.raises(ValueError, match="model"):
        make_client("openai", env={})


# -- the default stdlib transport, with urlopen mocked out ------------------------
class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_post_json_sends_json_and_decodes_reply(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["url"], seen["data"], seen["headers"] = request.full_url, request.data, dict(request.header_items())
        seen["method"] = request.get_method()
        return _Resp(b'{"ok": 1}')

    monkeypatch.setattr(http.urllib.request, "urlopen", fake_urlopen)
    assert http.post_json("http://x/y", {"x-api-key": "k"}, {"a": 1}) == {"ok": 1}
    assert seen["method"] == "POST" and json.loads(seen["data"]) == {"a": 1}
    assert seen["headers"]["Content-type"] == "application/json"
    assert seen["headers"]["X-api-key"] == "k"


def test_post_json_surfaces_http_errors(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"error": "bad key"}'))

    monkeypatch.setattr(http.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(LLMError) as info:
        http.post_json("http://x/y", {}, {})
    assert info.value.status == 401 and "bad key" in info.value.body


def test_post_json_surfaces_unreachable_and_non_json(monkeypatch):
    monkeypatch.setattr(http.urllib.request, "urlopen",
                        lambda r, timeout: (_ for _ in ()).throw(urllib.error.URLError("refused")))
    with pytest.raises(LLMError, match="could not reach"):
        http.post_json("http://x/y", {}, {})
    monkeypatch.setattr(http.urllib.request, "urlopen", lambda r, timeout: _Resp(b"<html>"))
    with pytest.raises(LLMError, match="non-JSON"):
        http.post_json("http://x/y", {}, {})
