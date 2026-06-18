from __future__ import annotations

import os
import sys

import httpx

BASE_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
EMAIL = os.getenv("SMOKE_EMAIL", "career.center@vinuni.edu.vn")
PASSWORD = os.getenv("SMOKE_PASSWORD", "password123")
IDENTITY_ID = os.getenv("SMOKE_IDENTITY_ID")
EXPECTED_PROVIDER = os.getenv("SMOKE_EXPECT_PROVIDER", "openrouter")
SMOKE_MODEL = os.getenv("SMOKE_MODEL", "nvidia/nemotron-3-nano-30b-a3b:free")


def main() -> int:
    with httpx.Client(base_url=BASE_URL, timeout=120.0) as client:
        token, identity_id = _login(client)
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Identity-Id": IDENTITY_ID or identity_id,
        }

        providers = client.get("/ai/providers", headers=headers).raise_for_status().json()
        _require(
            providers["chat_chain"][0] == EXPECTED_PROVIDER,
            f"chat_chain should start with {EXPECTED_PROVIDER}: {providers}",
        )
        _require(
            providers["embedding_chain"][0] == EXPECTED_PROVIDER,
            f"embedding_chain should start with {EXPECTED_PROVIDER}: {providers}",
        )
        _require(
            providers["rerank_chain"][0] == EXPECTED_PROVIDER,
            f"rerank_chain should start with {EXPECTED_PROVIDER}: {providers}",
        )

        chat_payload = {
            "messages": [
                {"role": "system", "content": "You are a concise assistant."},
                {
                    "role": "user",
                    "content": "Say VinUni OpenRouter AI is ready in one short sentence.",
                },
            ],
            "model": SMOKE_MODEL,
            "temperature": 0.1,
            "max_tokens": 80,
        }
        chat = client.post(
            "/ai/chat",
            headers=headers,
            json=chat_payload,
        ).raise_for_status().json()
        _require(
            chat["provider"] == EXPECTED_PROVIDER,
            f"chat provider should be {EXPECTED_PROVIDER}: {chat}",
        )

        embed = client.post(
            "/ai/embed",
            headers=headers,
            json={"text": "VinUni career matching with multilingual embeddings"},
        ).raise_for_status().json()
        _require(
            embed["provider"] == EXPECTED_PROVIDER,
            f"embedding provider should be {EXPECTED_PROVIDER}: {embed}",
        )
        minimum_dimension = 1 if EXPECTED_PROVIDER == "offline" else 100
        _require(
            len(embed["embedding"]) > minimum_dimension,
            "embedding vector should be non-trivial",
        )

        rerank = client.post(
            "/ai/rerank",
            headers=headers,
            json={
                "query": "backend internship with Python, FastAPI, and PostgreSQL",
                "documents": [
                    "Frontend React internship focused on animations.",
                    (
                        "Backend engineering internship using Python, FastAPI, "
                        "PostgreSQL, and cloud APIs."
                    ),
                    "Marketing assistant role with content writing.",
                ],
                "top_n": 2,
            },
        ).raise_for_status().json()
        _require(
            rerank["provider"] == EXPECTED_PROVIDER,
            f"rerank provider should be {EXPECTED_PROVIDER}: {rerank}",
        )
        _require(len(rerank["results"]) == 2, f"rerank should return top 2 results: {rerank}")

    print("AI smoke passed")
    print(f"- providers: {providers}")
    print(f"- chat: provider={chat['provider']} model={chat['model']}")
    print(
        f"- embed: provider={embed['provider']} "
        f"model={embed['model']} dim={len(embed['embedding'])}"
    )
    print(
        f"- rerank: provider={rerank['provider']} "
        f"model={rerank['model']} results={len(rerank['results'])}"
    )
    return 0


def _login(client: httpx.Client) -> tuple[str, str]:
    response = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    response.raise_for_status()
    data = response.json()
    identities = data.get("identities") or []
    _require(bool(identities), "demo user must have at least one identity")
    return str(data["access_token"]), str(identities[0]["id"])


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"AI smoke failed: {exc}", file=sys.stderr)
        raise
