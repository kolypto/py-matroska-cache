import itertools
from typing import TypeVar, Mapping, Union, Iterable, List

from sqlalchemy.orm.base import instance_state
from sqlalchemy.orm.relationships import RelationshipProperty
from sqlalchemy.orm.state import InstanceState

from matroska_cache.dep import PrimaryKey

SAInstanceT = TypeVar('SAInstanceT', bound=object)

# The dict used for plucking
PluckMap = Mapping[str, Union[int, 'PluckMap']]


def sa_dependencies(instance: Union[SAInstanceT, Iterable[SAInstanceT]], map: PluckMap, _seen: set = None) -> List[PrimaryKey]:
    """ Automatically collect PrimaryKey dependencies from SqlAlchemy instances

    Usage: when you have an output from a query, use sa_dependencies() on it to get a list of dependencies
    that you can provide to the MatroskaCache.put() function.
    NOTE: it will only pick primary key dependencies! Other dependencies can only be provided manually!

    Args:
        instance: the instance to get dependencies from
        map: inclusion map: {attribute: 1, relatiopnship: {key: 1, ...})
            Use `1` to include an attribute, dict() to include a relationship, `0` to exclude something
            NOTE: `map` must be valid!
    """
    if _seen is None:
        _seen = set()

    # Lists
    if isinstance(instance, (list, set, tuple)):
        return list(itertools.chain.from_iterable(
            sa_dependencies(item, map, _seen) for item in instance
        ))

    # Instances
    state: InstanceState = instance_state(instance)
    relationships: Mapping[str, RelationshipProperty] = state.mapper.relationships

    # Include self
    ret = []
    if instance not in _seen:
        ret.append(PrimaryKey.from_instance(instance))
    _seen.add(instance)

    # If there's anything left to iterate, do it
    if isinstance(map, dict):
        for key, include in map.items():
            # Skip excluded elements
            if not include:
                continue

            # Skip non-relationships
            if key not in relationships:
                # TODO: implement dependencies on individual attributes?
                continue

            # Descend into the relationship
            ret.extend(sa_dependencies(getattr(instance, key), include, _seen))

    return ret
