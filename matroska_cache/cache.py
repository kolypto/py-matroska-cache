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

from typing import Any

from .backends.base import MatroskaCacheBackendBase
from .dependency.base import DependencyBase


class MatroskaCache:
    def __init__(self, backend: MatroskaCacheBackendBase):
        self.backend = backend

    def get(self, key: str) -> Any:
        """ Get cached data by `key`; raise KeyError if it does not exist

        Args:
            key: The cache key
        Raises:
            KeyError: no data cached by that key
        """
        return self.backend.get(key)

    def has(self, key: str) -> bool:
        """ Check if there  """
        return self.backend.has(key)

    def put(self, key: str, data: Any, *dependencies: DependencyBase, expires: int):
        return self.backend.put(key, data, expires=expires, dependencies=dependencies)

    def invalidate(self, dependency: DependencyBase):
        return self.backend.invalidate(dependency)
