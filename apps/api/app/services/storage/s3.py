"""Almacenamiento S3 compatible (SeaweedFS en local, Cloudflare R2 en producción).

Dos clientes:
- interno: lo usa el backend para leer/escribir (http://seaweedfs:8333 en Docker)
- público: SOLO firma URLs con el host que ve el navegador (http://localhost:8333)
Firmar no hace ninguna llamada de red, así que el cliente público nunca conecta.
"""

import uuid
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self.ttl = settings.s3_presigned_ttl_seconds
        common = {
            "aws_access_key_id": settings.s3_access_key_id,
            "aws_secret_access_key": settings.s3_secret_access_key,
            "region_name": settings.s3_region,
            "config": Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        }
        self._internal = boto3.client("s3", endpoint_url=settings.s3_endpoint_url, **common)
        self._public = boto3.client("s3", endpoint_url=settings.s3_public_endpoint_url, **common)

    # -- Claves: el tenant SIEMPRE es el primer segmento --------------------------
    @staticmethod
    def document_key(tenant_id: uuid.UUID, document_id: uuid.UUID, name: str) -> str:
        return f"tenants/{tenant_id}/documents/{document_id}/{name}"

    # -- URLs firmadas ------------------------------------------------------------
    def presign_put(self, key: str, content_type: str) -> str:
        # ContentType queda dentro de la firma: el navegador debe enviar
        # exactamente ese Content-Type o S3 rechaza la subida.
        return str(
            self._public.generate_presigned_url(
                "put_object",
                Params={"Bucket": self.bucket, "Key": key, "ContentType": content_type},
                ExpiresIn=self.ttl,
            )
        )

    def presign_get(self, key: str, filename: str) -> str:
        disposition = f"inline; filename*=UTF-8''{quote(filename)}"
        return str(
            self._public.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": key,
                    "ResponseContentDisposition": disposition,
                    "ResponseContentType": "application/pdf",
                },
                ExpiresIn=self.ttl,
            )
        )

    # -- Operaciones del backend --------------------------------------------------
    def object_size(self, key: str) -> int | None:
        try:
            head = self._internal.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return int(head["ContentLength"])

    def read_range(self, key: str, start: int, end: int) -> bytes:
        obj = self._internal.get_object(Bucket=self.bucket, Key=key, Range=f"bytes={start}-{end}")
        return bytes(obj["Body"].read())

    def download(self, key: str, dest: Path) -> None:
        self._internal.download_file(self.bucket, key, str(dest))

    def upload(self, src: Path, key: str, content_type: str = "application/pdf") -> None:
        self._internal.upload_file(str(src), self.bucket, key, ExtraArgs={"ContentType": content_type})

    def delete(self, key: str) -> None:
        self._internal.delete_object(Bucket=self.bucket, Key=key)


@lru_cache
def get_storage() -> S3Storage:
    return S3Storage(get_settings())
