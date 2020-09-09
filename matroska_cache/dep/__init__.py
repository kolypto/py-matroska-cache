""" Cache dependencies """

from .id import Id
from .tag import Tag
from .ntag import NTag
from .scopes import Scopes

try:
    from .primary_key import PrimaryKey
except ImportError as e:
    pass
