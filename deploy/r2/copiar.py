"""Copia los archivos de la demo (bucket local de SeaweedFS) a Cloudflare R2 y verifica la copia.

Se ejecuta dentro del contenedor api-demo, que ya tiene boto3 y la configuración del bucket local:

    docker compose -f docker-compose.yml -f docker-compose.tunnel.yml exec -T \
        -e R2_ENDPOINT -e R2_ACCESS_KEY_ID -e R2_SECRET_ACCESS_KEY -e R2_BUCKET \
        api-demo python - < deploy/r2/copiar.py

Lee las credenciales de R2 del entorno y nunca las imprime. Es idempotente: no vuelve a subir un
objeto que ya está en R2 con el mismo tamaño. Ver docs/R2.md.
"""

import os
import sys

import boto3
from botocore.config import Config

from app.core.config import get_settings

CONFIG = Config(
    signature_version="s3v4",
    s3={"addressing_style": "path"},
    request_checksum_calculation="when_required",
    response_checksum_validation="when_required",
)


def objetos(cliente, bucket: str) -> dict[str, int]:  # type: ignore[no-untyped-def]
    salida: dict[str, int] = {}
    for pagina in cliente.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        salida.update({o["Key"]: o["Size"] for o in pagina.get("Contents", [])})
    return salida


def main() -> None:
    faltan = [v for v in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET") if not os.environ.get(v)]
    if faltan:
        sys.exit(f"Faltan en el entorno: {', '.join(faltan)}")
    s = get_settings()
    origen = boto3.client(
        "s3",
        endpoint_url=s.s3_endpoint_url,
        aws_access_key_id=s.s3_access_key_id,
        aws_secret_access_key=s.s3_secret_access_key,
        region_name=s.s3_region,
        config=CONFIG,
    )
    destino = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=CONFIG,
    )
    bucket_r2 = os.environ["R2_BUCKET"]
    en_origen = objetos(origen, s.s3_bucket)
    en_r2 = objetos(destino, bucket_r2)
    print(f"Origen {s.s3_bucket}: {len(en_origen)} objetos · R2 {bucket_r2}: {len(en_r2)} antes de copiar")

    copiados = 0
    for clave, tamano in sorted(en_origen.items()):
        if en_r2.get(clave) == tamano:
            continue
        obj = origen.get_object(Bucket=s.s3_bucket, Key=clave)
        destino.put_object(
            Bucket=bucket_r2,
            Key=clave,
            Body=obj["Body"].read(),
            ContentType=obj.get("ContentType", "application/octet-stream"),
        )
        copiados += 1
    print(f"Copiados: {copiados}")

    final = objetos(destino, bucket_r2)
    diferentes = [k for k, t in en_origen.items() if final.get(k) != t]
    if diferentes:
        sys.exit(f"✗ {len(diferentes)} objetos no coinciden en R2, por ejemplo: {diferentes[:3]}")
    total = sum(en_origen.values())
    print(f"✓ Los {len(en_origen)} objetos están en R2 con el mismo tamaño ({total / 1024:.0f} KB)")


main()
