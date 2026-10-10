"""Gemini through its OpenAI-compatible endpoint: no API key, no network."""
import json
from pathlib import Path

from portkit.agent.factory import make_client
from portkit.agent.loop import AgentSession, Message, ToolCall
from portkit.agent.openai import GEMINI_BASE_URL, OpenAIClient, from_openai_reply, to_openai_message
from portkit.agent.tools import SYSTEM_PROMPT, ToolBox
from portkit.agent.transcript import RecordingClient, ReplayClient, message_from_dict, message_to_dict

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fixtures" / "residue_mod" / "input"
SIG = {"google": {"thought_signature": "EpoGCpcGAXLI2nx/abc=="}}


class Recorder:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def __call__(self, url, headers, body):
        self.requests.append({"url": url, "headers": headers, "body": json.loads(json.dumps(body))})
        return self.replies.pop(0)


def gemini_call(call_id, name, usage=None, **args):
    reply = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": call_id, "type": "function", "extra_content": SIG,
         "function": {"name": name, "arguments": json.dumps(args)}}
    ]}}]}
    if usage:
        reply["usage"] = usage
    return reply


def gemini_text(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def test_factory_gemini_defaults_endpoint_and_key():
    rec = Recorder([gemini_text("hi")])
    client = make_client(
        env={"PORTKIT_LLM_PROVIDER": "gemini", "PORTKIT_LLM_MODEL": "gemini-3.8-flash", "GEMINI_API_KEY": "g-key"},
        transport=rec,
    )
    assert isinstance(client, OpenAIClient)
    client.complete([Message("user", "hi")], [])
    req = rec.requests[0]
    assert req["url"] == f"{GEMINI_BASE_URL}/chat/completions"
    assert req["url"] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert req["headers"]["authorization"] == "Bearer g-key"
    assert req["body"]["model"] == "gemini-3.8-flash"


def test_factory_gemini_base_url_override_wins():
    client = make_client(
        env={"PORTKIT_LLM_PROVIDER": "gemini", "PORTKIT_LLM_MODEL": "m", "PORTKIT_LLM_GEMINI_BASE_URL": "http://proxy/v1"},
    )
    assert client.base_url == "http://proxy/v1"
    client = make_client(config={"base_url": "http://cfg/v1"}, env={"PORTKIT_LLM_PROVIDER": "gemini", "PORTKIT_LLM_MODEL": "m"})
    assert client.base_url == "http://cfg/v1"


def test_a_global_gateway_url_does_not_capture_the_gemini_key():
    """#95: PORTKIT_LLM_BASE_URL saved for OpenRouter must not reroute gemini."""
    env = {"PORTKIT_LLM_PROVIDER": "gemini", "PORTKIT_LLM_MODEL": "m", "GEMINI_API_KEY": "g",
           "PORTKIT_LLM_BASE_URL": "https://openrouter.ai/api/v1"}
    assert make_client(env=env).base_url == GEMINI_BASE_URL


def test_the_global_base_url_still_serves_providers_without_a_default():
    env = {"PORTKIT_LLM_PROVIDER": "openai", "PORTKIT_LLM_MODEL": "m", "PORTKIT_LLM_BASE_URL": "https://openrouter.ai/api/v1"}
    assert make_client(env=env).base_url == "https://openrouter.ai/api/v1"
    env["PORTKIT_LLM_OPENAI_BASE_URL"] = "http://local:8080/v1"
    assert make_client(env=env).base_url == "http://local:8080/v1"


def test_gemini_native_has_its_own_base_url_variable():
    env = {"PORTKIT_LLM_PROVIDER": "gemini_native", "PORTKIT_LLM_MODEL": "m",
           "PORTKIT_LLM_GEMINI_NATIVE_BASE_URL": "https://proxy.example/v1beta/models"}
    assert make_client(env=env).base_url == "https://proxy.example/v1beta/models/m:generateContent"


def test_openai_provider_still_defaults_to_openai():
    client = make_client(env={"PORTKIT_LLM_PROVIDER": "openai", "PORTKIT_LLM_MODEL": "m"})
    assert client.base_url == "https://api.openai.com/v1"


def test_thought_signature_is_kept_and_sent_back(tmp_path):
    """The next request must carry the signature on the same tool call."""
    out = tmp_path / "out"
    rec = Recorder([gemini_call("c1", "list_source"), gemini_text("done")])
    client = OpenAIClient("gemini-3.8-flash", api_key="k", base_url=GEMINI_BASE_URL, transport=rec)
    session = AgentSession(client, ToolBox(SOURCE, out), SYSTEM_PROMPT)
    session.run("look around")
    second = rec.requests[1]["body"]["messages"]
    assistant = next(m for m in second if m["role"] == "assistant")
    call = assistant["tool_calls"][0]
    assert call["extra_content"] == SIG
    assert call["id"] == "c1" and call["function"]["name"] == "list_source"
    tool_reply = next(m for m in second if m["role"] == "tool")
    assert tool_reply["tool_call_id"] == "c1"


def test_extra_fields_cannot_override_core_call_fields():
    m = Message("assistant", tool_calls=[ToolCall("c1", "f", {"a": 1}, extra={"id": "evil", "x": 1})])
    call = to_openai_message(m)["tool_calls"][0]
    assert call["id"] == "c1" and call["type"] == "function" and call["x"] == 1


def test_plain_openai_calls_carry_no_extra():
    reply = {"choices": [{"message": {"tool_calls": [
        {"id": "c", "type": "function", "index": 0, "function": {"name": "f", "arguments": "{}"}}
    ]}}]}
    assert from_openai_reply(reply).tool_calls[0].extra == {}


def test_transcript_round_trips_signature_and_replays(tmp_path):
    msg = from_openai_reply(gemini_call("c1", "list_source"))
    assert message_from_dict(message_to_dict(msg)).tool_calls[0].extra == {"extra_content": SIG}

    path = tmp_path / "t.jsonl"
    rec = Recorder([gemini_call("c1", "list_source"), gemini_text("done")])
    live = OpenAIClient("gemini-3.8-flash", base_url=GEMINI_BASE_URL, transport=rec)
    AgentSession(RecordingClient(live, path), ToolBox(SOURCE, tmp_path / "a"), SYSTEM_PROMPT).run("go")
    assert "thought_signature" in path.read_text()
    replay = ReplayClient(path)
    AgentSession(replay, ToolBox(SOURCE, tmp_path / "b"), SYSTEM_PROMPT).run("go")
    assert replay.remaining == 0


def test_usage_counts_thinking_left_out_of_completion_tokens():
    # Gemini-style: thinking billed and in total_tokens, not in completion_tokens.
    usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 420}
    msg = from_openai_reply(gemini_call("c", "f", usage=usage))
    assert (msg.usage.input_tokens, msg.usage.output_tokens) == (100, 320)


def test_usage_openai_style_is_unchanged():
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    msg = from_openai_reply({"choices": [{"message": {"content": "x"}}], "usage": usage})
    assert (msg.usage.input_tokens, msg.usage.output_tokens) == (100, 50)
    no_total = {"prompt_tokens": 7, "completion_tokens": 3}
    msg = from_openai_reply({"choices": [{"message": {"content": "x"}}], "usage": no_total})
    assert (msg.usage.input_tokens, msg.usage.output_tokens) == (7, 3)


# === native-endpoint tests ======================================================
# The native Gemini endpoint at /v1beta/models/<id>:generateContent is what
# AI Studio auth-keys actually authorize (issue #95, OpenAI-compat path rejects
# auth keys with HTTP 400 "Please pass a valid API key"). URL and header per
# https://aistudio.google.com/docs/api-key.
NATIVE_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def native_text(text, finish_reason="STOP", usage=None):
    body = {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": finish_reason, "index": 0}]}
    if usage:
        body["usageMetadata"] = usage
    return body


def native_call(name, args, *, sig=None, finish_reason="STOP", usage=None):
    """A native reply that includes a functionCall part, optionally with a
    thought signature that must round-trip via ToolCall.extra."""
    part = {"functionCall": {"name": name, "args": args}}
    if sig is not None:
        part["thoughtSignature"] = sig
    body = {"candidates": [{"content": {"role": "model", "parts": [part]}, "finishReason": finish_reason, "index": 0}]}
    if usage:
        body["usageMetadata"] = usage
    return body


# --- 1. URL + headers ---------------------------------------------------------

def test_gemini_native_url_and_headers():
    rec = Recorder([native_text("hi")])
    client = make_client(
        env={"PORTKIT_LLM_PROVIDER": "gemini_native", "PORTKIT_LLM_MODEL": "gemini-3.1-pro-preview", "GEMINI_API_KEY": "g-key"},
        transport=rec,
    )
    from portkit.agent.gemini import GeminiClient
    assert isinstance(client, GeminiClient)
    client.complete([Message("user", "hi")], [])
    req = rec.requests[0]
    assert req["url"] == f"{NATIVE_BASE_URL}/gemini-3.1-pro-preview:generateContent"
    assert req["headers"]["x-goog-api-key"] == "g-key"
    assert req["headers"].get("authorization") is None
    # Model goes in the URL path on the native endpoint; never in the body.
    assert "model" not in req["body"]


# --- 2,3,4. Request body: messages, system, tools ------------------------------

def test_gemini_native_request_shape_no_system():
    rec = Recorder([native_text("ok")])
    client = make_client(
        env={"PORTKIT_LLM_PROVIDER": "gemini_native", "PORTKIT_LLM_MODEL": "m", "GEMINI_API_KEY": "k"},
        transport=rec,
    )
    client.complete([Message("user", "u1"), Message("assistant", "a1"), Message("user", "u2")], [])
    body = rec.requests[0]["body"]
    assert "systemInstruction" not in body
    assert body["contents"] == [
        {"role": "user", "parts": [{"text": "u1"}]},
        {"role": "model", "parts": [{"text": "a1"}]},
        {"role": "user", "parts": [{"text": "u2"}]},
    ]


def test_gemini_native_system_becomes_system_instruction():
    rec = Recorder([native_text("ok")])
    client = make_client(
        env={"PORTKIT_LLM_PROVIDER": "gemini_native", "PORTKIT_LLM_MODEL": "m", "GEMINI_API_KEY": "k"},
        transport=rec,
    )
    client.complete(
        [Message("system", "rules"), Message("user", "u1")],
        [],
    )
    body = rec.requests[0]["body"]
    assert body["systemInstruction"] == {"parts": [{"text": "rules"}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "u1"}]}]


def test_gemini_native_tool_definitions():
    rec = Recorder([native_text("ok")])
    client = make_client(
        env={"PORTKIT_LLM_PROVIDER": "gemini_native", "PORTKIT_LLM_MODEL": "m", "GEMINI_API_KEY": "k"},
        transport=rec,
    )
    schemas = [
        {
            "name": "read_source",
            "description": "Read a file from the Java mod being converted.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        },
        {
            "name": "validate",
            "description": "Run the Bedrock structural validator over the whole output tree.",
            "parameters": {"type": "object", "properties": {}},
        },
    ]
    client.complete([Message("user", "u")], schemas)
    body = rec.requests[0]["body"]
    decls = {d["name"]: d for d in body["tools"][0]["functionDeclarations"]}
    assert decls["read_source"]["description"].startswith("Read a file")
    assert decls["read_source"]["parameters"]["required"] == ["path"]
    assert "validate" in decls


# --- 5,6,7. Reply parsing + round-trips ---------------------------------------

def test_gemini_native_text_reply_round_trip():
    rec = Recorder([native_text("done", finish_reason="STOP",
                                usage={"promptTokenCount": 10, "candidatesTokenCount": 5, "thoughtsTokenCount": 100})])
    client = make_client(
        env={"PORTKIT_LLM_PROVIDER": "gemini_native", "PORTKIT_LLM_MODEL": "m", "GEMINI_API_KEY": "k"},
        transport=rec,
    )
    msg = client.complete([Message("user", "hi")], [])
    assert msg.role == "assistant"
    assert msg.content == "done"
    assert msg.tool_calls == []
    assert msg.finish_reason == "STOP"
    assert msg.usage.input_tokens == 10
    assert msg.usage.output_tokens == 105  # candidates + thoughts, for budget honesty


def test_gemini_native_tool_call_round_trip_preserves_thought_signature(tmp_path):
    """A thoughtSignature on the functionCall part must land in ToolCall.extra
    and be sent back on the next request, otherwise Gemini 3 rejects the turn
    (see test_thought_signature_is_kept_and_sent_back above for the
    OpenAI-compat equivalent)."""
    sig = "Eq8LCqwLAWkUfRMNwB3ww7a1TY9O/DnJZdrIW0zpyP1qzu2tetux4ocBvesU3CHJOgDL5Gk2g"
    out = tmp_path / "out"
    rec = Recorder([
        native_call("read_source", {"path": "x"}, sig=sig),
        native_text("done"),
    ])
    from portkit.agent.gemini import GeminiClient
    client = GeminiClient("m", api_key="k", transport=rec)
    session = AgentSession(client, ToolBox(SOURCE, out), SYSTEM_PROMPT)
    session.run("go")
    assert len(rec.requests) == 2
    # messages: [system, user("go"), assistant(reply1), tool(read_source), ...]
    first_reply = session.messages[2]
    assert first_reply.role == "assistant"
    assert first_reply.tool_calls
    assert first_reply.tool_calls[0].name == "read_source"
    assert first_reply.tool_calls[0].extra.get("thoughtSignature") == sig
    # On the 2nd request, the model message in contents must carry the signature back
    second = rec.requests[1]["body"]["contents"]
    model_msg = next(c for c in second if c["role"] == "model")
    parts = model_msg["parts"]
    assert any(p.get("thoughtSignature") == sig for p in parts)


def test_gemini_native_tool_results_folded_into_user_turn():
    """A Message('assistant', tool_calls=[...]) followed by Message('tool', ...)
    must collapse into one user turn with a functionResponse part — Gemini
    requires tool results inside a user-role content."""
    rec = Recorder([native_text("done")])
    from portkit.agent.gemini import GeminiClient
    client = GeminiClient("m", api_key="k", transport=rec)
    client.complete([
        Message("user", "u"),
        Message("assistant", "", tool_calls=[ToolCall("c1", "fn", {"a": 1})]),
        Message("tool", '{"ok": true}', tool_call_id="c1"),
        Message("user", "next"),
    ], [])
    body = rec.requests[0]["body"]
    contents = body["contents"]
    # Expect: user(u), model(tool_call), user(tool_result + "next"), or some valid
    # alternation that puts functionResponse inside a user-role content with no
    # consecutive user-role entries.
    roles = [c["role"] for c in contents]
    assert "user" in roles and "model" in roles
    # No two user-role contents in a row
    for a, b in zip(roles, roles[1:]):
        assert not (a == "user" and b == "user")
    # The functionResponse lives inside a user-role entry
    user_entries = [c for c in contents if c["role"] == "user"]
    fr_parts = [p for c in user_entries for p in c["parts"] if "functionResponse" in p]
    assert fr_parts, "functionResponse must appear inside a user-role content"


def test_gemini_native_factory_uses_gemini_api_key():
    """gemini_native reads GEMINI_API_KEY, not OPENAI_API_KEY, and registers as
    a distinct provider (additive — does not change the existing `gemini` entry)."""
    rec = Recorder([native_text("hi")])
    client = make_client(
        env={
            "PORTKIT_LLM_PROVIDER": "gemini_native",
            "PORTKIT_LLM_MODEL": "m",
            "GEMINI_API_KEY": "g-key",
            "OPENAI_API_KEY": "o-key",  # must be ignored
        },
        transport=rec,
    )
    from portkit.agent.gemini import GeminiClient
    assert isinstance(client, GeminiClient)
    assert client.api_key == "g-key"
    client.complete([Message("user", "hi")], [])
    assert rec.requests[0]["headers"]["x-goog-api-key"] == "g-key"


def test_gemini_native_extra_fields_kept_on_tool_call_round_trip(tmp_path):
    """Extra fields on a functionCall part that aren't part of {name, args}
    (e.g. provider-specific bookkeeping) must be carried in ToolCall.extra
    so the next request's contents include them under the model part."""
    part = {"functionCall": {"name": "fn", "args": {}}, "thoughtSignature": "abc"}
    reply = {"candidates": [{"content": {"role": "model", "parts": [part]}, "finishReason": "STOP", "index": 0}]}
    from portkit.agent.gemini import from_gemini_reply
    msg = from_gemini_reply(reply)
    assert msg.tool_calls[0].extra.get("thoughtSignature") == "abc"


# --- review fixes -------------------------------------------------------------

from portkit.agent.gemini import GeminiClient, from_gemini_reply, to_gemini_messages  # noqa: E402

NATIVE_ENV = {"PORTKIT_LLM_PROVIDER": "gemini_native", "PORTKIT_LLM_MODEL": "gemini-x", "GEMINI_API_KEY": "g-key"}


def test_gemini_native_ignores_a_global_gateway_base_url():
    rec = Recorder([native_text("hi")])
    env = {**NATIVE_ENV, "PORTKIT_LLM_BASE_URL": "https://openrouter.ai/api/v1"}
    make_client(env=env, transport=rec).complete([Message("user", "go")], [])
    assert rec.requests[0]["url"] == f"{NATIVE_BASE_URL}/gemini-x:generateContent"


def test_gemini_native_config_base_url_still_applies():
    rec = Recorder([native_text("hi")])
    client = make_client(config={"base_url": "https://proxy.example/v1beta/models/"}, env=NATIVE_ENV, transport=rec)
    client.complete([Message("user", "go")], [])
    assert rec.requests[0]["url"] == "https://proxy.example/v1beta/models/gemini-x:generateContent"


def test_gemini_native_temperature_goes_under_generation_config():
    rec = Recorder([native_text("hi")])
    make_client(env={**NATIVE_ENV, "PORTKIT_LLM_TEMPERATURE": "0.2"}, transport=rec).complete([Message("user", "go")], [])
    body = rec.requests[0]["body"]
    assert "temperature" not in body
    assert body["generationConfig"] == {"temperature": 0.2}
    rec2 = Recorder([native_text("hi")])
    GeminiClient("m", transport=rec2, extra={"max_tokens": 64, "stop": "END", "safetySettings": []}).complete(
        [Message("user", "go")], [])
    assert rec2.requests[0]["body"]["generationConfig"] == {"maxOutputTokens": 64, "stopSequences": ["END"]}
    assert rec2.requests[0]["body"]["safetySettings"] == []


def test_gemini_native_function_response_carries_the_function_name():
    _, contents = to_gemini_messages([
        Message("user", "go"),
        Message("assistant", tool_calls=[ToolCall("gemini_call_0", "read_source", {"path": "a"}),
                                         ToolCall("gemini_call_1", "validate", {})]),
        Message("tool", json.dumps({"text": "x"}), tool_call_id="gemini_call_0"),
        Message("tool", json.dumps(["not", "an", "object"]), tool_call_id="gemini_call_1"),
    ])
    responses = [p["functionResponse"] for p in contents[-1]["parts"]]
    assert [r["name"] for r in responses] == ["read_source", "validate"]
    assert responses[0]["response"] == {"text": "x"}
    assert responses[1]["response"] == {"result": ["not", "an", "object"]}


def test_gemini_native_blocked_or_contentless_replies_report_why():
    blocked = from_gemini_reply({"promptFeedback": {"blockReason": "SAFETY"}, "usageMetadata": {"promptTokenCount": 7}})
    assert blocked.content == "" and blocked.finish_reason == "SAFETY" and blocked.tool_calls == []
    no_content = from_gemini_reply({"candidates": [{"finishReason": "RECITATION", "index": 0}]})
    assert no_content.content == "" and no_content.finish_reason == "RECITATION"


def test_gemini_native_thought_parts_are_not_reply_text():
    reply = {"candidates": [{"content": {"role": "model", "parts": [
        {"text": "thinking about it", "thought": True}, {"text": "answer"}]}, "finishReason": "STOP"}]}
    assert from_gemini_reply(reply).content == "answer"
