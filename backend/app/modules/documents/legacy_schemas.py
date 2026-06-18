from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FileView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    uploader_id: str
    file_name: str
    file_url: str
    is_public: bool
    file_type: str


class SignedUrlResponse(BaseModel):
    url: str
    ttl_seconds: int
