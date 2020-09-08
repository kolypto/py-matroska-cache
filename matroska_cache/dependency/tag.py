from .base import DependencyBase, dataclass


@dataclass
class Tag(DependencyBase):
    """ Dependency on an arbitrary tag

    Usage:
        use this tag as a named signal to invalidate records

    Example:
        update_dashboard_for_admins = Tag('update-dashboard-for-admins')

        cache.put(
            'articles-list',
            [...],
            dependencies=[
                update_dashboard_for_admins,
                ...
            ]
        )

        cache.invalidate(update_dashboard_for_admins)
    """
    name: str
    __slots__ = 'name',

    PREFIX = 'tag'

    def key(self) -> str:
        return f'{self.PREFIX}:{self.name}'

