import pytest
from fakeredis import FakeRedis


@pytest.fixture()
def redis():
    return FakeRedis(encoding="utf-8", decode_responses=True)
