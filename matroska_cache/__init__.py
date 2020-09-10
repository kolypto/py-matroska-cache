__version__ = __import__('pkg_resources').get_distribution('matroska_cache').version


from .cache import MatroskaCache
from .exc import NotInCache
from . import dep

try:
    from .sa_tools import sa_dependencies, sa_modified_names
except ImportError:
    pass
