import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from zohra.services.chat import assistant_search as search
from zohra.services.chat import assistant_brain as brain_module
from zohra.services.chat import assistant_tools
from zohra.services.chat.assistant_store import AssistantStore


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///etc/passwd", "https://localhost/",
    "http://127.0.0.1/", "http://10.0.0.1/", "https://user:secret@example.org/",
    "https://example.org:8000/", "http://2130706433/", "https://demo.internal/",
    "https://example.org\\@localhost/", "https://example.org/\nfoo"])
def test_sources_reject_unsafe_or_private_links(url):
    assert search.public_source_url(url) is None


def test_search_returns_only_real_normalized_sources(monkeypatch):
    calls = []
    def provider(*args):
        calls.append(args)
        return [{"title": "<b>NASA</b> &amp; Moon", "href": "https://www.nasa.gov/",
                 "body": "<span>Mission</span> details", "date": "2026-09-26"},
                {"title": "duplicate", "url": "https://www.nasa.gov/"},
                {"title": "unsafe", "url": "http://localhost/"},
                {"title": "empty link"}]
    monkeypatch.setattr(search, "_search_provider", provider)
    result = search.search_web("NASA Moon", "news", 3, "w")
    assert calls == [("NASA Moon", "news", 3, "w")]
    assert result["status"] == "ok"
    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "NASA & Moon"
    assert result["results"][0]["snippet"] == "Mission details"
    assert result["results"][0]["published_at"] == "2026-09-26"
    assert result["retrieved_at"]
    assert "not been read" in result["evidence"]


@pytest.mark.parametrize("args", [{"query": ""}, {"query": "x" * 401}, {"query": []},
    {"query": "NASA", "max_results": True}, {"query": "NASA", "max_results": 6},
    {"query": "NASA", "kind": "image"}, {"query": "NASA", "recency": "all"},
    {"query": "NASA", "kind": "news", "recency": "y"}])
def test_invalid_search_never_reaches_network(monkeypatch, args):
    monkeypatch.setattr(search, "_search_provider", lambda *args: pytest.fail("Network called"))
    assert search.search_web(**args)["status"] == "invalid"


@pytest.mark.parametrize("query", ["api_key=abcd", "password:secret", "account number:12345",
    "email person@example.org", "my number 12345678901", "sk-or-v1-" + "x" * 40])
def test_credentials_and_contact_identifiers_never_leave_search(monkeypatch, query):
    monkeypatch.setattr(search, "_search_provider", lambda *args: pytest.fail("Network called"))
    assert search.search_web(query)["status"] == "blocked"


@pytest.mark.parametrize("failed", [False, True])
def test_search_unavailable_and_empty_have_no_mock_fallback(monkeypatch, failed):
    def provider(*args):
        if failed:
            raise TimeoutError("internal details")
        return []
    monkeypatch.setattr(search, "_search_provider", provider)
    result = search.search_web("NASA")
    assert result["results"] == []
    assert result["status"] == ("unavailable" if failed else "no_results")
    assert "internal details" not in json.dumps(result)


def test_news_recency_is_checked_when_provider_returns_old_or_future_results(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [{"title": "News", "url": f"https://example.org/{i}",
             "date": (now + timedelta(days=offset)).isoformat()} for i, offset in enumerate([-15, -2, 3])]
    monkeypatch.setattr(search, "_search_provider", lambda *args: rows)
    result = search.search_web("NASA", kind="news", recency="w")
    assert [row["url"] for row in result["results"]] == ["https://example.org/1"]


def test_structured_secret_redaction_does_not_corrupt_json(monkeypatch):
    monkeypatch.setattr(assistant_tools, "get_backend_update", lambda **args: {
        "source": "test", "data": {"api_key": "private", "nested": [{"password": "private"}],
                                  "status": "password:private", "balance": None}})
    result = assistant_tools.execute_tool("get_backend_update", {"domain": "system"})
    assert result["data"]["api_key"] == "[secret redacted]"
    assert result["data"]["nested"][0]["password"] == "[secret redacted]"
    assert result["data"]["balance"] is None
    assert "private" not in json.dumps(result)


def test_existing_conversation_database_migrates_and_keeps_sources(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT)")
        conn.execute("INSERT INTO messages VALUES (1, 'test', 'user', 'Hello')")
    store = AssistantStore(path)
    sources = [{"url": "https://www.nasa.gov/", "title": "NASA"}]
    store.add_message("test", "assistant", "Hello", sources)
    assert store.history("test") == [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hello"}]
    assert store.history("test", True)[1]["sources"] == sources


def test_search_loop_budget_and_sources_are_not_spoken(tmp_path, monkeypatch):
    brain = brain_module.AssistantBrain(AssistantStore(tmp_path / "assistant.db"))
    requests = []
    calls = [{"id": f"call-{i}", "type": "function", "function": {
        "name": "search_web", "arguments": json.dumps({"query": "NASA"})}} for i in range(3)]
    def respond(messages):
        requests.append(list(messages))
        return {"tool_calls": calls} if len(requests) == 1 else {"content": "NASA reports a mission. https://www.nasa.gov/"}
    monkeypatch.setattr(brain, "_request", respond)
    searches = []
    def lookup(**args):
        searches.append(args)
        return {"status": "ok", "retrieved_at": "now", "results": [{"title": "NASA",
            "url": "https://www.nasa.gov/", "publisher": "NASA", "published_at": None}]}
    monkeypatch.setattr(assistant_tools, "search_web", lookup)
    async def collect():
        return [event async for event in brain.run_reasoning_loop("test", "Search NASA")]
    events = asyncio.run(collect())
    assert events[0]["type"] == "acknowledgement"
    assert sum(event["type"] == "acknowledgement" for event in events) == 1
    assert len(searches) == 2
    source_event = next(event for event in events if event["type"] == "sources")
    assert len(source_event["sources"]) == 1
    reply = "".join(event["content"] for event in events if event["type"] == "token")
    assert "https://" not in reply
    assert brain.store.history("test", True)[-1]["sources"] == source_event["sources"]
    observations = [json.loads(row["content"]) for row in requests[-1] if row["role"] == "tool"]
    assert "budget" in observations[-1]["error"]
    asyncio.run(collect())
    prior = [row for row in requests[-1] if row["role"] == "assistant"]
    assert any("https://www.nasa.gov/" in row["content"] for row in prior)


def test_jokes_and_general_conversation_do_not_require_a_tool(tmp_path, monkeypatch):
    brain = brain_module.AssistantBrain(AssistantStore(tmp_path / "assistant.db"))
    monkeypatch.setattr(brain, "_request", lambda messages: {"content": "Why did the computer get cold? It left its Windows open."})
    async def collect():
        return [event async for event in brain.run_reasoning_loop("test", "Tell me a joke")]
    events = asyncio.run(collect())
    assert {event["type"] for event in events} == {"token"}
    assert "Windows" in "".join(event["content"] for event in events)


def test_unknown_or_financial_tools_do_not_get_a_work_promise():
    assert brain_module.work_acknowledgement("place_trade", "Do it") is None
    assert "karti" in brain_module.work_acknowledgement("search_web", "mujhe batao")


def test_spoken_answers_do_not_contain_emoji(tmp_path, monkeypatch):
    brain = brain_module.AssistantBrain(AssistantStore(tmp_path / "assistant.db"))
    monkeypatch.setattr(brain, "_request", lambda messages: {"content": "Hello! \U0001F604"})
    async def collect():
        return [event async for event in brain.run_reasoning_loop("test", "Hello")]
    assert "".join(event["content"] for event in asyncio.run(collect())) == "Hello!"
