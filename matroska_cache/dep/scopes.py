from __future__ import annotations

import warnings
from typing import Any, List, Callable, MutableMapping, Tuple, Union

from .base import DependencyBase, dataclass
from .tag import Tag

ExtractorFunc = Callable[[Any], dict]


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
        self._extractor_fns: MutableMapping[Tuple[str], ExtractorFunc] = {}

        # An invalidate-all dependency used to invalidate all caches in cases when scopes are not used properly.
        # For instance, the user is attempting to cache the results that matched a filter
        #   .condition(category_id=10)
        # but there was no extractor function that describes how `category_id` influences the cache.
        self._invalidate_all = InvalidateAll(self._object_type)
        self._production_mode = production_mode

    def describes(self, *param_names):
        """ Decorator for a function that extracts data for a conditional dependency.

        Whenever a new object is created, your application should call `invalidate_for()`,
        and it will invalidate every cache that depends on any filtered list of such objects.

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
        """
        def decorator(fn: ExtractorFunc):
            """ Register the decorated function and return """
            # Remember the extractor function and the parameters it returns
            filter_params_signature = tuple(sorted(param_names))
            assert filter_params_signature not in self._extractor_fns, (
                f'An extractor with filter parameters {filter_params_signature!r} is already described'
            )
            self._extractor_fns[filter_params_signature] = fn

            # Done
            return fn
        return decorator

    def invalidate_for(self, item: Any, cache: 'MatroskaCache', **info):
        """ Invalidate all caches that may see `item` in their listings.

        Args:
            item: The new/deleted item that may enter or leave the scope of some listing
            cache: MatroskaCache to invalidate
            **info: Extra info that may be passed to your extractor functions
        """
        cache.invalidate(*self.object_invalidates(item, **info))

    def condition(self, **conditions: Any) -> List[ConditionalDependency]:
        """ Get dependencies for a conditional scope.

        Use this method with MatroskaCache.put() to generate dependencies for your scope.

        Args:
            **conditions: The description of your filtering conditions, in the `name=value` form.

        Returns:
            List of scope dependencies to be used on your cache entry
        """
        # Signature
        filter_params_signature = tuple(sorted(conditions))

        if filter_params_signature in self._extractor_fns:
            return [
                ConditionalDependency(self._object_type, conditions),
                # Got to declare this kill switch as a dependency; otherwise, it won't work.
                self._invalidate_all,
            ]
        elif self._production_mode:
            warnings.want(
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

    def object_invalidates(self, item: Any, **info) -> List[Union[ConditionalDependency, InvalidateAll]]:
        """ Get dependencies that will invalidate all caches that may see `item` in their listings.

        This function takes the `item` and calls every extractor function decorated by `@scope.describes()`.
        The resulting value will be used to find scopes that this object will come into, and invalidate them.

        Args:
            item: The newly created or freshly deleted item.
            **info: Additional arguments to pass to *all* the extractor functions.

        Returns:
            List of dependencies to be used with `cache.invalidate()`
        """
        ret = []
        for param_names, extractor_fn in self._extractor_fns.items():
            # Run the extractor function
            try:
                params = extractor_fn(item, **info)
            except Exception:
                # In production mode, just invalidate all
                if self._production_mode:
                    return [self._invalidate_all]
                # In development mode, report the error
                else:
                    raise

            # If it returned a correct set of fields (as @describes()ed), generate a dependency
            if set(params) == set(param_names):
                ret.append(ConditionalDependency(self._object_type, params))
            # In production mode, just invalidate all
            elif self._production_mode:
                return [self._invalidate_all]
            # In development mode, report an error
            else:
                raise RuntimeError(
                    f'The described extractor {extractor_fn} was supposed to return a dict of {param_names!r}, '
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


class InvalidateAll(Tag):
    """ A custom tag, used in production, to invalidate all scopes in cases when Scopes is misconfigured """

    # Use the same prefix. Not important; just looks nice
    # There will be no clashes because all `ConditionalDependency` have "&" in their names
    PREFIX = ConditionalDependency.PREFIX

    def __init__(self, object_type: str):
        super().__init__(f'{object_type}')
