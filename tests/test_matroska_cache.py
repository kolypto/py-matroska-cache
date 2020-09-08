import dataclasses

import pytest
import sqlalchemy as sa
import sqlalchemy.ext.declarative
from fakeredis import FakeRedis

from matroska_cache import MatroskaCache, dep
from matroska_cache import sa_dependencies
from matroska_cache.backends.redis import RedisBackend
from .lib import sa_set_committed_state


def test_cache_plain_dependencies(redis: FakeRedis):
    """ Test Matroska cache with plain dependencies """
    cache = MatroskaCache(backend=RedisBackend(redis, prefix='cache'))

    # Test: cache a simple object
    data = [{'id': 1}, {'id': 2}]
    cache.put(
        'articles-list', data,
        dep.Id('article', 1),
        dep.Id('article', 2),
        expires=1000,
    )

    # Get it back
    value = cache.get('articles-list')
    assert value == data

    # Invalidate some random missing thing
    cache.invalidate(dep.Tag('hop'))
    assert cache.has('articles-list')

    # Now invalidate one of the alerts
    cache.invalidate(dep.Id('article', 1))

    # No data anymore
    assert not cache.has('articles-list')
    with pytest.raises(KeyError):
        cache.get('articles-list')


def test_cache_sa_dependencies(redis: FakeRedis):
    """ Test sa_dependencies() """
    def main():
        cache = MatroskaCache(backend=RedisBackend(redis, prefix='cache'))

        # Prepare data
        author = sa_set_committed_state(User(), id=1)
        articles = [
            sa_set_committed_state(Article(), id=10, author_id=author.id, author=author),
            sa_set_committed_state(Article(), id=11, author_id=author.id, author=author),
        ]

        # Plucking map
        # This is the map that's going to be used to convert models to json
        pluck_map = {'id': 1, 'title': 1, 'author': {'id': 1, 'login': 1}}

        # sa_dependencies()
        # Test results
        dependencies = sa_dependencies(articles, pluck_map)
        assert [dataclasses.asdict(d) for d in dependencies] == [
            # 3 dependencies
            # Note that the `User` is mentioned only once.
            # sa_dependencies() should detect instances that have already been visited
            {'type': 'Article', 'id': '10'},
            {'type': 'User', 'id': '1'},
            {'type': 'Article', 'id': '11'},
        ]

        # Test: cache a simple object
        data = ['...']  # for the test, it does not really matter what data we store
        cache.put(
            'articles-list', data,
            *dependencies,
            expires=1000,
        )

        # Get it back
        value = cache.get('articles-list')
        assert value == data

        # Invalidate
        cache.invalidate(dep.RawPrimaryKey('User', 1))
        assert not cache.has('articles-list')

    # Sample models
    Base = sa.ext.declarative.declarative_base()

    class User(Base):
        __tablename__ = 'users'
        id = sa.Column(sa.Integer, primary_key=True)
        login = sa.Column(sa.String)

        articles = sa.orm.relationship(lambda: Article, back_populates='author')

    class Article(Base):
        __tablename__ = 'articles'
        id = sa.Column(sa.Integer, primary_key=True)
        title = sa.Column(sa.String)

        author_id = sa.Column(sa.ForeignKey(User.id))
        author = sa.orm.relationship(User, back_populates='articles')

    # main
    main()
