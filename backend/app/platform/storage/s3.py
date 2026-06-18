from __future__ import annotations

from app.platform.storage.protocols import StoredObject
from app.shared.errors import AppError, ErrorCode


class S3Storage:
    def __init__(
        self,
        *,
        bucket: str | None,
        endpoint_url: str | None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ) -> None:
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        if not bucket:
            raise AppError(
                code=ErrorCode.INTERNAL_ERROR,
                message="S3 storage selected but S3_BUCKET is not configured",
                status_code=500,
            )

    def put_bytes(self, key: str, content: bytes, content_type: str) -> StoredObject:
        clean_key = key.lstrip("/").replace("..", "_")
        client = self._client()
        client.put_object(
            Bucket=self.bucket,
            Key=clean_key,
            Body=content,
            ContentType=content_type,
        )
        return StoredObject(
            key=clean_key,
            url=self.signed_url(clean_key, ttl_seconds=900),
            content_type=content_type,
            size_bytes=len(content),
        )

    def signed_url(self, key: str, ttl_seconds: int) -> str:
        return self._client().generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )

    def presigned_upload(
        self,
        key: str,
        content_type: str,
        ttl_seconds: int,
    ) -> dict[str, object]:
        clean_key = key.lstrip("/").replace("..", "_")
        url = self._client().generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": clean_key,
                "ContentType": content_type,
            },
            ExpiresIn=ttl_seconds,
        )
        return {"url": url, "method": "PUT", "fields": {}}

    def _client(self):
        try:
            import boto3
        except ImportError as exc:
            raise AppError(
                code=ErrorCode.INTERNAL_ERROR,
                message="boto3 is required for S3/R2 storage",
                status_code=500,
            ) from exc

        kwargs = {}
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        if self.access_key_id and self.secret_access_key:
            kwargs["aws_access_key_id"] = self.access_key_id
            kwargs["aws_secret_access_key"] = self.secret_access_key
        return boto3.client("s3", **kwargs)
