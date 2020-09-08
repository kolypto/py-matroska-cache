""" Cache dependencies """

from .id import Id
from .tag import Tag

try:
    from .primary_key import PrimaryKey, RawPrimaryKey
except ImportError as e:
    pass
