"""The /v1 routes end to end over HTTP, against a real database and the real
embedding model."""
from __future__ import annotations


async def _chat(client, message: str, conversation_id: str | None = None) -> dict:
    body = {"message": message, "history": []}
    if conversation_id:
        body["conversation_id"] = conversation_id
    response = await client.post("/v1/chat", json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def _verify(client) -> dict:
    response = await client.get("/v1/integrity/verify")
    assert response.status_code == 200, response.text
    return response.json()


async def test_chat_stores_extracted_memories_and_keeps_integrity(client):
    data = await _chat(client, "I live in Bangalore and I like Python")

    assert sorted(m["text"] for m in data["stored_memories"]) == ["location: Bangalore", "preference: Python"]
    assert data["failed_candidates"] == 0
    memories = (await client.get("/v1/memories")).json()
    assert memories["total"] == 2
    verify = await _verify(client)
    assert not verify["tampered"]
    assert verify["leaf_count"] == 2


async def test_contradicting_update_versions_the_same_memory(client):
    first = await _chat(client, "I live in Bangalore")
    conversation_id = first["conversation_id"]
    second = await _chat(client, "I live in Mumbai", conversation_id)

    memory_id = first["stored_memories"][0]["memory_id"]
    assert second["stored_memories"][0]["memory_id"] == memory_id
    detail = (await client.get(f"/v1/memories/{memory_id}")).json()
    assert detail["version_count"] == 2
    assert detail["text"] == "location: Mumbai"
    assert (await client.get("/v1/memories")).json()["total"] == 1


async def test_logs_show_each_events_own_version_decision(client):
    first = await _chat(client, "I live in Bangalore")
    await _chat(client, "I live in Mumbai", first["conversation_id"])

    logs = (await client.get("/v1/logs")).json()
    assert logs["total"] == 2
    for item in logs["items"]:
        trust = (await client.get(f"/v1/trust/{item['version_id']}")).json()
        assert item["decision"] == trust["decision"]
        assert item["trust_score"] == trust["trust_score"]


async def test_tamper_route_is_caught_by_verify(client):
    stored = (await _chat(client, "I like Python"))["stored_memories"][0]

    response = await client.post("/v1/attack/tamper-db", json={"version_id": stored["version_id"]})
    assert response.status_code == 200, response.text

    verify = await _verify(client)
    assert verify["tampered"]
    assert [m["version_id"] for m in verify["row_mismatches"]] == [stored["version_id"]]


async def test_inject_poison_then_rollback_recovers_cleanly(client):
    await _chat(client, "I live in Bangalore")
    memory_id = (await client.get("/v1/memories")).json()["items"][0]["memory_id"]

    injected = await client.post(
        "/v1/attack/inject-poison", json={"text": "location: Atlantis", "memory_id": memory_id}
    )
    assert injected.status_code == 200, injected.text
    poisoned_version_id = injected.json()["version_id"]

    rollback = await client.post(f"/v1/rollback/{poisoned_version_id}", json={"triggered_by": "test"})
    assert rollback.status_code == 200, rollback.text
    assert [a["outcome"] for a in rollback.json()["affected"]] == ["reverted"]

    detail = (await client.get(f"/v1/memories/{memory_id}")).json()
    assert detail["text"] == "location: Bangalore"
    assert not (await _verify(client))["tampered"]


async def test_rollback_of_a_superseded_version_keeps_the_newer_state(client):
    first = await _chat(client, "I live in Bangalore")
    stale_version_id = first["stored_memories"][0]["version_id"]
    memory_id = first["stored_memories"][0]["memory_id"]
    await _chat(client, "I live in Mumbai", first["conversation_id"])

    response = await client.post(f"/v1/rollback/{stale_version_id}", json={"triggered_by": "test"})

    assert response.status_code == 200, response.text
    assert [a["outcome"] for a in response.json()["affected"]] == ["superseded"]
    assert (await client.get(f"/v1/memories/{memory_id}")).json()["text"] == "location: Mumbai"
    assert not (await _verify(client))["tampered"]


async def test_admin_reset_reseeds_the_demo_chain(client):
    await _chat(client, "I like Rust")

    response = await client.post("/v1/admin/reset")
    assert response.status_code == 200, response.text

    texts = sorted(m["text"] for m in (await client.get("/v1/memories")).json()["items"])
    assert len(texts) == 3
    assert "preference: Python" in texts
    assert not (await _verify(client))["tampered"]


async def test_model_status_reports_rule_only_with_bootstrap_off(client):
    status = (await client.get("/v1/trust/model")).json()
    assert status["mode"] == "rule_only"


async def test_analytics_counts_trust_gate_decisions_not_rollback_writes(client):
    # Regression (audit B14): every version ever written was counted as a
    # decision, so a rollback's own versions inflated store/reject.
    await _chat(client, "I live in Bangalore and I like Python")
    memory_versions = [m["current_version_id"] for m in (await client.get("/v1/memories")).json()["items"]]
    rollback = await client.post(f"/v1/rollback/{memory_versions[0]}", json={"triggered_by": "test"})
    assert rollback.status_code == 200, rollback.text

    summary = (await client.get("/v1/analytics/summary")).json()

    assert sum(summary["decision_counts"].values()) == 2
    assert sum(p["store"] + p["review"] + p["reject"] for p in summary["trend"]) == 2
    assert sum(p["rollbacks"] for p in summary["trend"]) == 1
    assert summary["total_versions"] == 3  # the rollback's version still exists, it just isn't a decision
