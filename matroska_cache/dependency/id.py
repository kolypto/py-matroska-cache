from typing import Union

from .base import DependencyBase, dataclass


@dataclass
class Id(DependencyBase):
    """ Dependency on an id of some object

    Usage:
        when the cached data includes an object, use its id to declare a dependency

    Example:
        cache.put(
            'articles-list',
            [
                Article(id=1).asdict(),
                Article(id=2).asdict(),
            ],
            dependencies=[
                Id('article', 1),
                Id('article', 2),
            ]
        )

        cache.invalidate(
            Id('article', 1)
        )
    """
    type: str
    id: Union[int, str]
    __slots__ = 'type', 'id'

    PREFIX = 'id'

    def key(self) -> str:
        return f'{self.PREFIX}:{self.type}:{self.id}'
