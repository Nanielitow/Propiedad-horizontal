from typing import Any

from app.core.rate_limit import Limit, hit


class FakeRedis:
    def __init__(self, fail: bool = False) -> None:
        self.data: dict[str, int] = {}
        self.ttl: dict[str, int] = {}
        self.fail = fail

    async def incr(self, name: str) -> int:
        if self.fail:
            raise ConnectionError("redis caído")
        self.data[name] = self.data.get(name, 0) + 1
        return self.data[name]

    async def expire(self, name: str, time: int) -> Any:
        self.ttl[name] = time


LIMIT = Limit("test", 3, 60, "x")


async def test_permite_hasta_el_limite_y_luego_bloquea() -> None:
    redis = FakeRedis()
    results = [await hit(redis, LIMIT, "u1", now=1000.0) for _ in range(4)]
    assert results[:3] == [None, None, None]
    assert results[3] == 20  # 1000 % 60 = 40 -> faltan 20 s para la nueva ventana


async def test_cada_sujeto_tiene_su_propio_contador() -> None:
    redis = FakeRedis()
    for _ in range(3):
        await hit(redis, LIMIT, "u1", now=1000.0)
    assert await hit(redis, LIMIT, "u2", now=1000.0) is None


async def test_la_ventana_siguiente_reinicia_el_contador() -> None:
    redis = FakeRedis()
    for _ in range(4):
        await hit(redis, LIMIT, "u1", now=1000.0)
    assert await hit(redis, LIMIT, "u1", now=1021.0) is None  # nueva ventana (1020-1079)


async def test_expira_la_clave_solo_al_crearla() -> None:
    redis = FakeRedis()
    await hit(redis, LIMIT, "u1", now=1000.0)
    await hit(redis, LIMIT, "u1", now=1000.0)
    assert list(redis.ttl.values()) == [60]


async def test_si_redis_falla_se_permite_la_peticion() -> None:
    assert await hit(FakeRedis(fail=True), LIMIT, "u1") is None
