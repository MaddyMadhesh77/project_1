from types import SimpleNamespace

from app.services.llm_client import ClaudeLLMClient, history_for_api


def test_history_starting_with_assistant_is_trimmed_to_first_user_turn():
    history = [
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a2"},
    ]
    assert history_for_api(history) == history[1:]
    assert history_for_api([{"role": "assistant", "content": "a"}]) == []
    assert history_for_api([]) == []


class _FakeMessages:
    def __init__(self, text):
        self.calls, self._text = [], text

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self._text)])


def _client(text):
    client = ClaudeLLMClient.__new__(ClaudeLLMClient)
    client._model = "claude-sonnet-5"
    client._client = SimpleNamespace(messages=_FakeMessages(text))
    return client


async def test_reply_sends_valid_history_with_thinking_disabled():
    client = _client("hi")
    await client.reply("now", [{"role": "assistant", "content": "orphan"}, {"role": "user", "content": "u"}])
    call = client._client.messages.calls[0]
    assert call["messages"][0]["role"] == "user"
    assert call["thinking"] == {"type": "disabled"}


async def test_judge_parses_number_with_thinking_disabled():
    client = _client("0.9")
    assert await client.judge_contradiction("a", "b") == 0.9
    assert client._client.messages.calls[0]["thinking"] == {"type": "disabled"}
