from .tag import Tag, dataclass


@dataclass
class NTag(Tag):
    """ Namespaced tag that uses its class name as the prefix.

    Use it in a large application to have more control over prefixes
    """
    PREFIX = ...

    def __init_subclass__(cls):
        cls.PREFIX = cls.__name__
