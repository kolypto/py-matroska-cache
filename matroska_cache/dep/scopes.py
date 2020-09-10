from __future__ import annotations

import warnings
from typing import Any, List, Callable, Tuple, Union, Collection, FrozenSet, Optional, Iterable, Set

from .base import DependencyBase, dataclass
from .tag import Tag


ExtractorFunc = Callable[[Any], Optional[dict]]


class Scopes:
    """ Generate dependencies that describe lists of objects.

    This tool is designed to solve the case where newly created, or freshly removed, items may enter the scope
    of some listing, which may itself be filtered by some condition.

    In general, if you cache a list of objects by `Id`:

        cache.put(
            'articles-list', [...],
            dep.Id('article', 1),
            dep.Id('article', 2),
            ...
        )

    you will not have this list of articles invalidated when new articles come into scope.

    For instance, if your view caches the list of articles by `category`, intialize the `Scopes` object like this:

        article_scopes = Scopes('article', production_mode=False)

        @article_scopes.describes('category')
        def article_category(article: Article):
            return {'category': article.category}

    This operation enables us to use `category` information as a dependency for the cached list:

        # Articles filtered by category ...
        articles = ssn.query(Article).filter_by(category='python').all()
        cache.put(
            f'articles-list:category=python',  # make sure to put it here
            articles,
            ...
            # ... declare this category as their dependency
            *article_scopes.condition(category='python')
        )

    Now, in another place, where articles are created, you can invalidate this dependency automatically
    by just passing the new article to the article_scopes.invalidate_for() method:

        def create_new_article(...):
            ...
            article_scopes.invalidate_for(article, invalidate_for)

    Under the hood, it will go over every condition known through @article_scopes.describes()
    and invalidate all related caches.

    ---

    NOTE: Does it seem complicated to you?
    It is; but this complexity follows one goal: to make caching *declarative* and minimize hidden connections in your code.
    For instance, you could have used Tag() to achieve the very same result.
    Listing articles:

        articles = ssn.query(Article).filter_by(category='python').all()
        cache.put(
            f'articles-list:category=python',  # make sure to put it here
            articles,
            ...
            # ... declare this category as their dependency
            dep.Tag(f'articles:category=python'),
        )

    Adding articles:

        cache.invalidate(dep.Tag(f'books:category={article.category}'))

    This code would work just fine; but then, for every caching behavior you would need *to remember* to add another line
    to the place where articles are saved. Those connections would soon become numerous and lead to caching errors that
    are hard to catch.

    This approach with `Scopes()` is a declarative approach:
    you first declare *the intention* of caching by category, and `Scopes()` will check that everything is set up properly.
    """
    def __init__(self, object_type: str, *, production_mode: bool):
        """ Initialize scopes for a particular kind of object

        Args:
            object_type: Name for the objects you're watching. Got to be unique. Example: 'article'
            production_mode: Whether the cache is currently operating on a production server.
                If there is an error with how you configured the `Scopes` object, its will be disabled.
                In development (production_mode=False), an exception will be raised.
        """
        self._object_type = object_type
        self._extractor_fns: List[ExtractorInfo] = []
        self._known_extractor_signatures: Set[Tuple[str]] = set()

        # An invalidate-all dependency used to invalidate all caches in cases when scopes are not used properly.
        # For instance, the user is attempting to cache the results that matched a filter
        #   .condition(category_id=10)
        # but there was no extractor function that describes how `category_id` influences the cache.
        self._invalidate_all = InvalidateAll(self._object_type)
        self._production_mode = production_mode

    def describes(self, *param_names, watch_modified: Optional[Iterable[str]] = None):
        """ Decorator for a function that extracts data for a conditional dependency.

        NOTE: let your function return `None` if you want a particular change to be ignored for some reason.

        Whenever any object is saved, your application should call `invalidate_for()`,
        and it will invalidate every cache that might see a new object enter the scope, or an old one leave it.

        The arguments for the scope are described by the decorated function: if you want to cache the results of
        a list filtered by `category=<something>`, you first need to define an extractor function:

            @article_scopes.describes('category')
            def article_category(article: Article, **info):
                # Extract filter arguments from a new object
                return {'category': article.category}

        Only after such a condition is described, you can use it as a cache key:

            cache.put(
                f'articles-{category}',
                articles,
                ...,
                *article_scopes.condition(category=category),
                expires=600,
            )

        Note that the values extracted by `article_category()` and provided to `condition()` have to match.
        If they don't, cache will misbehave.

        Args:
            *param_names: The list of parameter names the extractor function is going to return.
                These names are completely custom, but have to match those given to condition()
            watch_modified: Only run this function when the following fields are modified.
                Default: equal to `parameter_names`.
                Setting this field manually only makes sense when your parameter names are different from attribute names.
                For example:
                    return {'filter-by-category': article.category}
        """
        def decorator(fn: ExtractorFunc):
            """ Register the decorated function and return """
            self._extractor_fns.append(
                ExtractorInfo(
                    param_names=frozenset(param_names),
                    watch_modified=frozenset(watch_modified) if watch_modified else frozenset(param_names),
                    func=fn
                )
            )
            self._known_extractor_signatures.add(tuple(sorted(param_names)))

            # Done
            return fn
        return decorator

    def invalidate_for(self, item: Any, cache: 'MatroskaCache', modified: Collection[str] = None, **info):
        """ Invalidate all caches that may see `item` in their listings.

        Args:
            item: The new/deleted item that may enter or leave the scope of some listing
            cache: MatroskaCache to invalidate
            modified: (optional) list of field names that have been modified. Useful to ignore non-relevant updates.
            **info: Extra info that may be passed to your extractor functions
        """
        cache.invalidate(*self.object_invalidates(item, modified, **info))

    def condition(self, **conditions: Any) -> List[Union[ConditionalDependency, InvalidateAll]]:
        """ Get dependencies for a conditional scope.

        Use this method with MatroskaCache.put() to generate dependencies for your scope.

        Args:
            **conditions: The description of your filtering conditions, in the `name=value` form.

        Returns:
            List of scope dependencies to be used on your cache entry
        """
        # Signature
        filter_params_signature = tuple(sorted(conditions))

        if filter_params_signature in self._known_extractor_signatures:
            return [
                ConditionalDependency(self._object_type, conditions),
                # Got to declare this kill switch as a dependency; otherwise, it won't work.
                self._invalidate_all,
            ]
        elif self._production_mode:
            warnings.warn(
                f'Matroska cache: no extractor @describes for {filter_params_signature!r}. '
                f'Caching disabled. '
            )
            return [self._invalidate_all]
        else:
            raise RuntimeError(
                f'No extractor function is described for condition {filter_params_signature!r}. '
                f'Please use @.describes() on a function with matching parameters. '
                f'It will not fail in production, but caching will be disabled.'
            )

    def object_invalidates(self, item: Any, modified: Collection[str] = None, **info) -> List[Union[ConditionalDependency, InvalidateAll]]:
        """ Get dependencies that will invalidate all caches that may see `item` in their listings.

        This function takes the `item` and calls every extractor function decorated by `@scope.describes()`.
        The resulting value will be used to find scopes that this object will come into, and invalidate them.

        Args:
            item: The newly created or freshly deleted item.
            modified: (optional) list of field names that have been modified. Useful to ignore non-relevant updates.
                If not provided, all extractor functions will be run to invalidate dependencies.
                If provided, only those that are watching those attributes will be run.
            **info: Additional arguments to pass to *all* the extractor functions.

        Returns:
            List of dependencies to be used with `cache.invalidate()`
        """
        if modified:
            modified = set(modified)

        ret = []
        for extractor_info in self._extractor_fns:
            # if `modified` was provided, skip extractors that are not interested in those fields
            if modified and not (extractor_info.watch_modified & modified):
                continue

            # Run the extractor function and get dependency parameters
            try:
                params = extractor_info.func(item, **info)
            except Exception:
                # In production mode, just invalidate all
                if self._production_mode:
                    return [self._invalidate_all]
                # In development mode, report the error
                else:
                    raise

            # If the function returned a None, skip it altogether
            if params is None:
                continue
            # If it returned a correct set of fields (as @describes()ed), generate a dependency
            elif set(params) == extractor_info.param_names:
                ret.append(ConditionalDependency(self._object_type, params))
            # In production mode, just invalidate all
            elif self._production_mode:
                return [self._invalidate_all]
            # In development mode, report an error
            else:
                raise RuntimeError(
                    f'The described extractor {extractor_info.func} was supposed to return a dict of {extractor_info.param_names!r}, '
                    f'but it returned only {params!r}. Please fix. '
                    f'It will not fail in production, but caching will be disabled.'
                )
        return ret


@dataclass
class ConditionalDependency(DependencyBase):
    """ Internal dependency used by Scope

    A dependency object of this type is generated for the output of every extractor function.
    This is how the whole thing operates:

    When a new article is created, it is passed to the `invalidate_for()` function.
    An extractor function, described like this:

            @article_scopes.describes('category')
            def article_category(article: Article, **info):
                # Extract filter arguments from a new object
                return {'category': article.category}

    will generate a dependency:

        ConditionalDependency(object_type='article', conditions={'category': 'sci-fi'})
        # it is just a string:
        'condition:article:&category=sci-fi&'

    This string invalidates any cache entries that had been created like this:

            cache.put(
                ...
                *article_scopes.condition(category=category),
            )

    So, in essense, this whole Scopes is just an interface to match the two strings in a declarative fashion.
    """
    object_type: str
    condition: str
    __slots__ = 'object_type', 'condition',

    def __init__(self, object_type: str, conditions: dict):
        self.object_type = object_type
        self.condition = '&'.join(f'{key}={value}'
                                  # items are sorted to make sure they always match in the same way!
                                  for key, value in sorted(conditions.items()))
        # Surround it with &s to enable wildcard matching
        self.condition = '&' + self.condition + '&'

    PREFIX = 'condition'

    def key(self) -> str:
        return f'{self.PREFIX}:{self.object_type}:{self.condition}'


@dataclass
class ExtractorInfo:
    # Set of parameters that the extractor function promises to return
    param_names: FrozenSet[str]

    # Set of parameters that it watches the modifications on.
    # Default: equal to param_names_set
    watch_modified: FrozenSet[str]

    # The extractor function itself
    func: ExtractorFunc

    __slots__ = 'param_names', 'watch_modified', 'func'



class InvalidateAll(Tag):
    """ A custom tag, used in production, to invalidate all scopes in cases when Scopes is misconfigured """

    # Use the same prefix. Not important; just looks nice
    # There will be no clashes because all `ConditionalDependency` have "&" in their names
    PREFIX = ConditionalDependency.PREFIX

    def __init__(self, object_type: str):
        super().__init__(f'{object_type}')
