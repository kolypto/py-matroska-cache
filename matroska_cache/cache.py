""" Matroska cache handles the caching of objects with dependency tracking.

Example:
    cache = MatroskaCache(RedisBackend(redis=self.redis, prefix='cache'))

    # Cache a piece of JSON data
    cache.put(
        # The cache key
        'users-list',
        # The data
        [
            {'id': 1, ...},
            {'id': 2, ...},
        ]
        # Dependencies. If any of them is updated, the whole cache key goes down
        dep.Id('user', 1),
        dep.Id('user', 2),
        # Cache time
        expires=60,
    )

    # Get the cache
    cache.get('users-list')

    # Invalidate the cache
    cache.invalidate(dep.Id('user', 1))

    # No cache anymore
    cache.has('users-list')  #-> False

When working with SqlAlchemy models, however, you may want to use some special tools :)
sa_dependencies() will automatically collect primary key dependencies:

Example:

    data = ssn.query(Article).options(
        joinedload(Article.author)
    ).all()

    dependencies = sa_dependencies(data, {'author': 1})
    # -> [
    #    PrimaryKey('Article', 1),
    #    PrimaryKey('Article', 2),
    #    PrimaryKey('Author', 1),
    # ]

    cache.put('articles-list', jsonify(data), *dependencies, expires=60)
"""
import logging
from datetime import timedelta
from typing import Any, Union

from .backends.base import MatroskaCacheBackendBase
from .dep.base import DependencyBase
from .exc import NotInCache  # noqa

logger = logging.getLogger(__name__)


class MatroskaCache:
    def __init__(self, backend: MatroskaCacheBackendBase):
        self.backend = backend

    def get(self, key: str) -> Any:
        """ Get cached data by `key`; raise KeyError if it does not exist

        Args:
            key: The cache key
        Raises:
            NotInCache: no data cached by that key
        """
        return self.backend.get(key)

    def has(self, key: str) -> bool:
        """ Check if cache key `key` is available """
        return self.backend.has(key)

    def put(self, key: str, data: Any, *dependencies: DependencyBase, expires: Union[int, timedelta]):
        """ Store data into the cache under key `key`

        Args:
            key: The cache key
            data: The data to store. It has to be json-serializable.
            *dependencies: List of dependencies for this cache entry. See `matroska_cache.dep`.
            expires: The number of seconds to keep this cache entry for, or a `timedelta` object
        """
        if isinstance(expires, timedelta):
            expires = int(expires.total_seconds())
        self.log_enabled and logger.info('put(): ' + ", ".join(str(dep) for dep in dependencies))
        return self.backend.put(key, data, expires=expires, dependencies=dependencies)

    def delete(self, key: str):
        """ Delete a cache key """
        self.backend.delete(key)

    def invalidate(self, *dependencies: DependencyBase):
        """ Invalidate all cache entries that depend on `dependencies`

        Args:
            *dependencies: List of dependencies to invalidate cache records for
        """
        self.log_enabled and logger.info('invalidate(): ' + ", ".join(str(dep) for dep in dependencies))
        return self.backend.invalidate(dependencies)

    log_enabled: bool = False

    def set_logging_enabled(self, enabled: bool):
        """ Buff: +7 to your debugging skills """
        self.log_enabled = enabled
        self.backend.log_enabled = enabled
