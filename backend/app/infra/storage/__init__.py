from app.infra.storage.factory import get_storage
from app.infra.storage.protocols import StorageClient, StoredObject

__all__ = ["StorageClient", "StoredObject", "get_storage"]
