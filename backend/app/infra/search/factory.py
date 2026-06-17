from __future__ import annotations

from functools import lru_cache

from app.core.config import settings
from app.infra.search.external import ExternalSearchClient
from app.infra.search.memory import MemorySearchClient
from app.infra.search.protocols import SearchClient


@lru_cache
def get_search_client() -> SearchClient:
    if settings.search_backend in {"opensearch", "elasticsearch"}:
        return ExternalSearchClient(
            backend=settings.search_backend,
            url=settings.search_url,
            index_prefix=settings.search_index_prefix,
            api_key=settings.search_api_key,
            username=settings.search_username,
            password=settings.search_password,
        )
    return MemorySearchClient()
