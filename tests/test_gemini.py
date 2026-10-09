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
        env={"PORTKIT_LLM_PROVIDER": "gemini", "PORTKIT_LLM_MODEL": "m", "PORTKIT_LLM_BASE_URL": "http://proxy/v1"},
    )
    assert client.base_url == "http://proxy/v1"


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
