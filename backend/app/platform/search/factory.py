from __future__ import annotations

from functools import lru_cache

from app.platform.search.external import ExternalSearchClient
from app.platform.search.memory import MemorySearchClient
from app.platform.search.protocols import SearchClient
from app.shared.config import settings


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
