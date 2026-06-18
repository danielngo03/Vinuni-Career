from app.platform.search.factory import get_search_client
from app.platform.search.protocols import SearchClient, SearchDocument, SearchHit

__all__ = ["SearchClient", "SearchDocument", "SearchHit", "get_search_client"]
