[![Tests](https://github.com/kolypto/py-matroska-cache/workflows/Tests/badge.svg)](/kolypto/py-matroska-cache/actions)
[![Pythons](https://img.shields.io/badge/python-3.7%E2%80%933.8-blue.svg)](noxfile.py)

Matroska Cache: Cache with dependency tracking
==============================================

["Matroska"](https://en.wikipedia.org/wiki/Matryoshka_doll), aka Russian Doll, 
is a nesting doll where one is placed inside another.

In Python, Matroska is a cache with nested objects that knows when they change.
This is implemented as *dependency tracking*:

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
            'articles-list', data,
            # Describe its dependencies. 
            # If any of the articles gets modified, the whole cache key will be discarded
            dep.Id('article', 1),
            dep.Id('article', 2),
            dep.Id('author', 1),
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
