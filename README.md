[![Tests](https://github.com/kolypto/py-matroska-cache/workflows/Tests/badge.svg)](/kolypto/py-matroska-cache/actions)
[![Pythons](https://img.shields.io/badge/python-3.7%E2%80%933.8-blue.svg)](noxfile.py)

Matroska Cache with dependency tracking
=======================================

*I solved the cache invalidation problem. Couldn't find a good name for it, though*.

Matroska🪆 is a cache handler with nested objects that knows when they change.
This is implemented through *dependency tracking*:

```python
from redis import Redis
from matroska_cache import MatroskaCache, dep
from matroska_cache.backends.redis import RedisBackend

redis = Redis('losthost', 6379, db=0)
cache = MatroskaCache(RedisBackend(redis, prefix='cache'))

def get_articles_list():
    # if cached content is available, use it
    if cache.has('articles-list'):
        return cache.get('articles-list')
    # load the data from the database if not
    else:
        # Data loaded from the database
        author = {'id': 1, 'name': 'kolypto'}
        data = [
            {'id': 1, 'title': 'Python', 'author': author},
            {'id': 2, 'title': 'Cache', 'author': author},
        ]

        # Put it into cache
        cache.put(
            # Cache key
            'articles-list', 
            # The data to cache
            data,
            # Describe its dependencies. 
            # If any of the articles gets modified, the whole cache key will be discarded
            dep.Id('article', 1),
            dep.Id('article', 2),
            dep.Id('author', 1),
            expires=60,  # seconds
        )
        
        # Done
        return data
```

Now the articles list is cached using `articles-list` as the key.
The cached list will be *invalidated* if any user or article gets modified:

```python
def modify_user(id: int):
    ...
    # Invalidate any cache entries that depend on this author
    cache.invalidate(
        dep.Id('author', id)
    )

def modify_article(id: int):
    ...
    # Invalidate any cache entries that depend on this article
    cache.invalidate(
        dep.Id('article', id)
    )
```

Installation
------------

Install with pip:

> pip install matroska-cache



Lists Tracking using Scopes
---------------------------

The example given above suffers from a tragic flaw: it tracks changes made to individual items, but it won't notice
when a newly created item enters the scope of your articles list.

This is what `Scopes` is made for.
Suppose you have a view that lists published articles that are also filtered by category:

```python
from sqlalchemy.orm import Session
from matroska_cache import MatroskaCache, NotInCache, sa_dependencies

cache: MatroskaCache
session: Session

def articles_view(category: str):
    cache_key = f'articles-list:published=True;category={category}'
    
    # Get from cache, if cached
    try:
        return cache.get(cache_key)
    # Query the database, if not
    except NotInCache:
        # Load articles from the database
        articles = session.query(Article).filter(
            # Load only a few articles
            Article.published == True,
            Article.category == category,
        )

        cache.put(
            # Cache the data
            cache_key, articles,
            # 🎀 Automatically generate primary key dependencies for SqlAlchemy instances
            # The second argument tells to generate dependencies for the "author" relationship as well
            *sa_dependencies(articles, {'author': 1}),
            expires=60,
        )
```  

Now, you can of course invalidate the whole cache whenever any article is created or removed,
but we can do better than that.

First, let us define a `Scope`, and a function which will extract `published` and `category` parameters
from newly created/deleted articles:

```python
from matroska_cache import dep

# Scopes: an object that helps you track changes to lists
article_scopes = dep.Scopes('Article', production_mode=False)

# Describe a function that extracts parameters for your filter.
# We are going to filter by `published` and `category`, so we extract them and return.
# The decorator tells which fields we are going to extract.
@article_scopes.describes('published', 'category')
def extract(article: Article):
    return {'published': article.published, 'category': article.category} 

``` 

Now, having declared such a function, we find a place in the code where Articles are saved,
and tell `article_scopes` about that by calling `invalidate_for()`.

Note that because a scope has already been declared and described, you don't have to do anything special.
You just give an object to the scope, and that's it. 

```python
from matroska_cache import sa_modified_names

# NOTE: consider using SqlAlchemy Session events for this.

def create_article():
    ...
    article_scopes.invalidate_for(article, cache)

def delete_article():
    ...
    article_scopes.invalidate_for(article, cache)

def modify_article():
    ...
    # Note that in this case you have to give it the list of modified parameters.
    # sa_modified_names() helps you with that.
    # Why is that important? Because some changes are relevant (published, category) while others are not.
    article_scopes.invalidate_for(article, cache, sa_modified_names(article)
```

Finally, when you have a scope declared, described, and bound to your CRUD, use it as a dependency:

```python
    cache.put(
        ...,
        *article_scopes.condition(category=category)
    )
```

No one said it would be easy. But it works.

Appendix
========

["Matroska"](https://en.wikipedia.org/wiki/Matryoshka_doll), aka Russian Doll 🪆, 
is a nesting doll where one is placed inside another.

*There are only two hard things in Computer Science: cache invalidation and naming things.*
