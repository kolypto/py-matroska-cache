__version__ = __import__('pkg_resources').get_distribution('matroska_cache').version


from .cache import MatroskaCache
from .exc import NotInCache
from . import dependency as dep

try:
    from .sa_dependencies import sa_dependencies
except ImportError:
    pass
