from typing import Tuple, Any, Union

from sqlalchemy.orm.base import instance_state
from sqlalchemy.orm.state import InstanceState

from .id import Id, dataclass


@dataclass()
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
                PrimaryKey(Article, 1),
                PrimaryKey(Article, 2),
            ]
        )

        cache.invalidate(
            Id('article', 1)
        )
    """

    PREFIX = 'pk'

    def __init__(self, model: Union[str, type], identity: Union[str, int]):
        if isinstance(model, type):
            model = model.__name__
        super().__init__(model, identity)

    @classmethod
    def from_instance(cls, instance: object):
        state: InstanceState = instance_state(instance)
        return cls(
            state.class_.__name__,
            cls._instance_identity_to_str(state.identity)
        )

    @classmethod
    def _instance_identity_to_str(cls, identity: Tuple[Any]) -> str:
        # For models with singular primary key, just stringify it
        if len(identity) == 1:
            return str(identity[0])
        # For models with composite primary key, repr() its tuple
        else:
            return repr(identity)
