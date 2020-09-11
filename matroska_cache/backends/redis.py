import itertools
import json
import logging
from typing import Any, Iterable, List

from redis import Redis, WatchError

from .base import MatroskaCacheBackendBase, DependencyBase, NotInCache

logger = logging.getLogger(__name__)


class RedisBackend(MatroskaCacheBackendBase):
    def __init__(self, redis: Redis, *, prefix: str):
        """ Init the Redis backend for the matroska cache

        Args:
            redis: Redis client
            prefix: Prefix string for our cache keys
        """
        self.redis = redis
        self.prefix = prefix

    def get(self, key: str) -> Any:
        # Get the data; fail if the key does not exist
        data = self.redis.get(self._key('data', key))
        if data is None:
            raise NotInCache(key)

        # Unserialize
        return unserialize(data)

    def has(self, key: str) -> bool:
        return self.redis.exists(self._key('data', key)) == 1

    def delete(self, key: str):
        self.redis.unlink(self._key('data', key))

    def put(self, key: str, data: Any, dependencies: Iterable[DependencyBase], expires: int):
        data_key = self._key('data', key)

        # Store the dependency information
        self._remember_dependencies_for(data_key, dependencies, expires)

        # Store the data
        self.redis.setex(data_key, expires, serialize(data))

    def invalidate(self, dependencies: Iterable[DependencyBase]):
        if not dependencies:
            return

        # Get the list of keys that depend on `dependency` (every single one of them)
        # Use a set to ensure their uniqueness
        deps = {self._key('rdep', dependency.key())
                for dependency in dependencies}

        # Atomically, in a transaction
        with self.redis.pipeline() as t:
            # It's scary to do `while True`, so we only try 10 times
            for _ in range(0, 10):
                try:
                    # Fail the transaction if any of those keys gets changed
                    t.watch(*deps)

                    # Get the data keys to invalidate
                    # To get the data keys, we load every reverse-dependency key
                    with t.pipeline(transaction=False) as p:
                        for rdep_key in deps:
                            p.smembers(rdep_key)
                        data_keys = list(itertools.chain(*p.execute()))

                    # Invalidate those data keys
                    # Invalidate dependency keys as well. Otherwise they may accumulate lots of dead data keys
                    if data_keys:
                        # Also watch the data keys we've just obtained
                        t.watch(*data_keys)

                        # Atomically delete everything
                        t.multi()
                        t.unlink(*data_keys, *deps)
                        t.execute()

                    # Great success!
                    self.log_enabled and logger.info('Invalidated data keys: ' + ' ; '.join(data_keys))
                    break
                except WatchError:
                    # Conflict. Retry.
                    continue

    def _remember_dependencies_for(self, data_key: str, dependencies: Iterable[DependencyBase], expires: int):
        """ Update dependency information for `key`

        This method stores two keys:
        * fdep: forward dependency information: { data-key => set(dependency, ...) }
        * rdep: reverse dependency information: { dependency => set(data-key, ...) }

        After storing those, it updates the expiration time on every dependency key:
        sets it to `expires`, but makes sure that the resulting TTL is not getting shorter
        """
        # Dependencies as a string with "rdep::" prefix
        # Use a set to ensure their uniqueness
        deps = {self._key('rdep', dependency.key())
                for dependency in dependencies}
        if not deps:
            return

        # 1. Store reverse dependency information: `dep` is a depencency of `data`
        #    Format: "rdep:<dependency>" = set(<data-key>, ...)
        # 2. Extend the expiration time of these keys
        #    Because many data keys may share dependencies, we can never cut the expiration time short;
        #    we can only prolong it.
        #
        # So, in Redis terms:
        # for every dependency `dep` in `deps`:
        #   SADD <dep> <key>
        #   TTL <dep>
        #   if <expires> greater than <ttl>:
        #       EXPIRE <dep> <expires>

        # Add `data_key` as a reverse dependency of every `deps`
        # We'll use a pipeline to speed things up. We don't need a transaction here, because we want this data to be saved anyway
        p = self.redis.pipeline(transaction=False)
        for dep in deps:
            p.sadd(dep, data_key)
        p.execute()

        # Extend the TTLs
        # Use a transaction becase we have to (read, update, write) atomically
        with self.redis.pipeline() as t:
            for _ in range(0, 10):
                try:
                    # Fail the transaction if any of those keys gets changed
                    t.watch(*deps)

                    # Get all TTLs at once
                    with t.pipeline(transaction=False) as p:
                        for dep in deps:
                            p.ttl(dep)
                        dep_ttls: List[int] = p.execute()

                    # Only update keys that have a TTL shorter than this.
                    # This makes sure that we only prolong TTLs, never cut them short
                    expire_deps = [
                        dep
                        for dep, dep_ttl in zip(deps, dep_ttls)
                        if dep_ttl < expires
                    ]

                    # Atomically update them all.
                    # Note that we're still under WATCH ;)
                    t.multi()
                    for dep in expire_deps:
                        t.expire(dep, expires)
                    t.execute()

                    # Great success!
                    break
                except WatchError:
                    # Conflict. Retry.
                    continue

    def _key(self, type: str, name: str):
        """ Make a Redis key name

        Args:
            type: The type of information stored in the key.
                'data': the data cached by the user
                'fdep': forward dependencies
            name: Cache key
        """
        return f'{self.prefix}::{type}::{name}'


def serialize(data: Any):
    """ Serialize strings and objects efficiently

    String: returned as is, with 's' as a prefix
    Json: serialized, using 'j' as the prefix

    With plain strings, this is 14x faster
    """
    if isinstance(data, str):
        return DATA_STRING + data
    else:
        return DATA_JSON + json.dumps(data)


def unserialize(data: Any):
    format, data = data[0], data[1:]
    if format == DATA_STRING:
        return data
    elif format == DATA_JSON:
        return json.loads(data)


# Prefixes for data formats
DATA_STRING = 's'
DATA_JSON = 'j'
