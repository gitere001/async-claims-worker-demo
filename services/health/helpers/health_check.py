import asyncio
import socket
import ssl
from typing import Tuple, Dict

import asyncpg
import pika
import redis.asyncio as aioredis

from config.app_settings import settings

DATABASE_URL  = settings.get("database_url", "")
RABBIT_MQ_URL = settings.get("rabbitmq_url", "")
REDIS_URL     = settings.get("redis_url", "")


async def check_database() -> Tuple[bool, Dict[str, str]]:
    try:
        # asyncpg needs the raw postgresql:// URL — strip the +asyncpg driver prefix
        dsn = DATABASE_URL.replace("postgresql+asyncpg", "postgresql")
        conn = await asyncpg.connect(dsn=dsn)
        await conn.close()
        return True, {"database": "OK"}
    except Exception as e:
        return False, {"database": f"UNHEALTHY: {e}"}


def check_rabbitmq() -> Tuple[bool, Dict[str, str]]:
    try:
        # pika misparses the trailing // in amqp://host:port// as an empty vhost.
        # Replace it with the URL-encoded default vhost /%2F so pika reads it correctly.
        url = RABBIT_MQ_URL.rstrip("/") + "/%2F" if RABBIT_MQ_URL.endswith("//") else RABBIT_MQ_URL
        params = pika.URLParameters(url)

        if RABBIT_MQ_URL.startswith("amqps://"):
            ctx = ssl.create_default_context()
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED
            params.ssl_options = pika.SSLOptions(ctx)

        with pika.BlockingConnection(params) as conn:
            if conn.is_open:
                return True, {"rabbitmq": f"OK ({params.host}:{params.port})"}

        return False, {"rabbitmq": "UNHEALTHY: connection closed immediately"}

    except Exception as e:
        return False, {"rabbitmq": f"UNHEALTHY: {e}"}


async def check_redis() -> Tuple[bool, Dict[str, str]]:
    try:
        client = aioredis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        await asyncio.wait_for(client.ping(), timeout=3.0)
        await client.aclose()
        return True, {"redis": "OK"}

    except (asyncio.TimeoutError, socket.timeout) as e:
        return False, {"redis": f"UNHEALTHY: timeout ({e})"}
    except Exception as e:
        return False, {"redis": f"UNHEALTHY: {type(e).__name__}: {e}"}
