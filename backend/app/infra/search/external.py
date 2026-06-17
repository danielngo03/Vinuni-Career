from __future__ import annotations

import httpx

from app.api.exceptions import AppError, ErrorCode
from app.infra.search.protocols import SearchDocument, SearchHit


class ExternalSearchClient:
    def __init__(
        self,
        *,
        backend: str,
        url: str | None,
        index_prefix: str,
        api_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.backend = backend
        self.url = url.rstrip("/") if url else None
        self.index_prefix = index_prefix
        self.api_key = api_key
        self.username = username
        self.password = password
        if not url:
            raise AppError(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"{backend} search backend selected but SEARCH_URL is not configured",
                status_code=500,
            )

    def index(self, document: SearchDocument) -> None:
        payload = {
            "entity_type": document.entity_type,
            "title": document.title,
            "body": document.body,
            "metadata": document.metadata,
            "embedding": document.embedding,
        }
        self._request("PUT", f"/{self._index(document.entity_type)}/_doc/{document.id}", payload)

    def search(
        self,
        query: str,
        *,
        entity_type: str | None = None,
        embedding: list[float] | None = None,
        limit: int = 10,
    ) -> list[SearchHit]:
        index = self._index(entity_type or "*")
        payload = {
            "size": limit,
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "body", "metadata.*"],
                    "fuzziness": "AUTO",
                }
            },
        }
        data = self._request("POST", f"/{index}/_search", payload)
        hits = []
        for item in data.get("hits", {}).get("hits", []):
            source = item.get("_source", {})
            document = SearchDocument(
                id=item.get("_id", ""),
                entity_type=source.get("entity_type", entity_type or "unknown"),
                title=source.get("title", ""),
                body=source.get("body", ""),
                metadata=source.get("metadata", {}),
                embedding=source.get("embedding"),
            )
            hits.append(
                SearchHit(
                    document=document,
                    score=float(item.get("_score", 0.0) or 0.0),
                    reasons={"backend": self.backend, "vector_requested": bool(embedding)},
                )
            )
        return hits

    def _index(self, entity_type: str) -> str:
        return f"{self.index_prefix}-{entity_type}"

    def _request(self, method: str, path: str, payload: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        auth = None
        if self.api_key:
            headers["Authorization"] = f"ApiKey {self.api_key}"
        elif self.username and self.password:
            auth = (self.username, self.password)
        try:
            with httpx.Client(timeout=15.0, auth=auth) as client:
                response = client.request(
                    method,
                    f"{self.url}{path}",
                    headers=headers,
                    json=payload,
                )
            response.raise_for_status()
            return response.json() if response.content else {}
        except httpx.HTTPError as exc:
            raise AppError(
                code=ErrorCode.UPSTREAM_UNAVAILABLE,
                message=f"{self.backend} request failed",
                status_code=503,
                details={"error": str(exc), "path": path},
            ) from exc
