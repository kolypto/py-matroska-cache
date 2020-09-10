import itertools
import json
import logging
from typing import Any, Iterable, List

from redis import Redis

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
        # Store the dependency information
        self._remember_dependencies_for(key, dependencies, expires)

        # Store the data
        self.redis.setex(self._key('data', key), expires, serialize(data))

    def invalidate(self, dependencies: Iterable[DependencyBase]):
        if not dependencies:
            return

        # Get the list of keys that depend on `dependency` (every single one of them)
        # This is resolved through the `rdep` key
        rdep_keys = [self._key('rdep', dependency.key())
                     for dependency in dependencies]
        p = self.redis.pipeline()
        for rdep_key in rdep_keys:
            p.smembers(rdep_key)
        data_keys = list(itertools.chain(*p.execute()))

        self.log_enabled and logger.info('Invalidating data keys: ' + ' ; '.join(data_keys))

        # Invalidate every data key that depend on these rdep_keys
        # This means deleting them
        if data_keys:  # do nothing if there is nothing to do
            self.redis.unlink(*(self._key('data', key) for key in data_keys))

    def _remember_dependencies_for(self, key: str, dependencies: Iterable[DependencyBase], expires: int):
        """ Update dependency information for `key`

        This method stores two keys:
        * fdep: forward dependency information: { data-key => set(dependency, ...) }
        * rdep: reverse dependency information: { dependency => set(data-key, ...) }

        After storing those, it updates the expiration time on every dependency key:
        sets it to `expires`, but makes sure that the resulting TTL is not getting shorter
        """
        # Dependencies as a string
        deps = [dependency.key() for dependency in dependencies]
        if not deps:
            return

        # Use a pipeline to speed up
        p = self.redis.pipeline()

        # # Forward dependency information: `data` depends on `dep`
        # NOTE: this information might only be useful for debugging
        # fdep_key = self._key('fdep', key)
        # p.sadd(fdep_key, *deps)

        # Reverse dependency information: `dep` is a dependency of `data`
        rdep_keys = []
        for dep in deps:
            rdep_key = self._key('rdep', dep)
            rdep_keys.append(rdep_key)
            p.sadd(rdep_key, key)

        # Commit
        p.execute()

        # Get the current TTLs for dependency keys
        dep_keys = rdep_keys  #[fdep_key, *rdep_keys]
        for key in dep_keys:
            p.ttl(key)
        dep_keys_ttls: List[int] = p.execute()

        # Prolong every TTL if `expires` is beyond that.
        dep_keys_expire = [max(ttl, expires) for ttl in dep_keys_ttls]

        # Update TTLs for dep keys
        for key, key_expires in zip(key, dep_keys_expire):
            p.expire(key, key_expires)
        p.execute()

    def _key(self, type: str, name: str):
        """ Make a Redis key name

        Args:
            type: The type of information stored in the key.
                'data': the data cached by the user
                'fdep': forward dependencies
            name: Cache key
        """
        return f'{self.prefix}::{type}::{name}'


serialize = json.dumps
unserialize = json.loads
