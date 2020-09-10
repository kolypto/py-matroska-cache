""" Cache back-end for Matroska Cache.

It's primary task is to handle dependencies when the following operations are made:

* put(data, key, dependencies)
* get(key)
* invalidate(dependencies)

Example put():
    put(
        data=[
            Article(id=1, author=User(12)).asdict(),
            Article(id=2, author=User(12)).asdict(),
        ],
        key='articles-list',
        dependencies=[
            Id('article', 1),
            Id('article', 2),
            Id('author', 12),
        ],
    )

Example get():
    get('articles-list')

Example invalidate:
    invalidate(
        dependencies=[
            Id('author', 12),
        ]
    )
"""

from abc import ABC, abstractmethod
from typing import Any, Iterable

from matroska_cache.dep.base import DependencyBase
from matroska_cache.exc import NotInCache  # noqa


class MatroskaCacheBackendBase(ABC):
    log_enabled: bool = False

    @abstractmethod
    def put(self, data: Any, key: str, *, expires: int, dependencies: Iterable[DependencyBase]):
        """ Put `data` into cache, keyed by `key`, depending on `dependencies`

        Args:
            data: The data to put into cache
            key: The key under which caching is done. Has to be unique.
            dependencies: The list of objects that the data in cache depends on.
                If any of those dependencies becomes invalid, this piece of data will be invalidated as well.
            expires: The number of seconds the data will expire in
        """

    @abstractmethod
    def get(self, key: str) -> Any:
        """ Get a piece of cached data, if still available

        Args:
            key: The cache key
        Returns:
            cached data
        Raises:
            NotInCache: no data found
        """

    @abstractmethod
    def has(self, key: str) -> bool:
        """ See whether the cache has `key` stored in it """

    @abstractmethod
    def delete(self, key: str):
        """ Remove cached data by key """

    @abstractmethod
    def invalidate(self, dependencies: Iterable[DependencyBase]):
        """ Invalidate all cache records with `dependency` as their dependency """
