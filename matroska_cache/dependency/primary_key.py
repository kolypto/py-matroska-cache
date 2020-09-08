from typing import Tuple, Any

from sqlalchemy.orm.base import instance_state
from sqlalchemy.orm.state import InstanceState

from .id import Id


class PrimaryKey(Id):
    """ Dependency on a primary key of an instance

    Usage:
        when the cached data includes an SqlAlchemy instance, use its primary key to declare a dependency

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

    PREFIX = 'pk'

    def __init__(self, instance: object):
        state: InstanceState = instance_state(instance)
        super().__init__(
            type=state.class_.__name__,
            id=self._instance_identity_to_str(state.identity)
        )

    def _instance_identity_to_str(self, identity: Tuple[Any]) -> str:
        if len(identity) == 1:
            return str(identity[0])
        else:
            return repr(identity)


class RawPrimaryKey(Id):
    """ A primary key dependency that you will have to construct manually ;) """
    PREFIX = 'pk'
