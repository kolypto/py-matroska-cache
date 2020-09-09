import dataclasses
from typing import MutableMapping

import pytest
import sqlalchemy as sa
import sqlalchemy.ext.declarative
from fakeredis import FakeRedis

from matroska_cache import MatroskaCache, dep, NotInCache
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
    with pytest.raises(NotInCache):
        cache.get('articles-list')

    # Test delete()
    cache.put('test', 1, expires=10)
    assert cache.has('test')
    cache.delete('test')
    assert not cache.has('test')


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


def test_collection_dependencies(redis: FakeRedis):
    """ Test dynamic dependencies """
    cache = MatroskaCache(backend=RedisBackend(redis, prefix='cache'))

    book_scopes = dep.Scopes('book', production_mode=False)

    @book_scopes.describes('category')
    def book_category(book: dict):
        return {'category': book['category']}


    def main():
        # Test that cache is invalidated when:
        # * a sci-fi book is added
        # * a sci-fi book is modified
        # Test that cache is NOT invalidated when:
        # * any other book is added or modified

        # Known sci-fi books
        expected_scifi = []

        # First list(): empty list
        assert list_scifi_books() == (False, expected_scifi)  # no cached value
        assert list_scifi_books() == (True, expected_scifi)  # cache hit

        # Add a book.
        add_other_book(category='fantasy')
        assert list_scifi_books() == (True, expected_scifi)  # cache is still hit: this category is not cached

        # Add a Sci-Fi book
        add_scifi_book()
        expected_book = {'id': 2, 'category': 'sci-fi'}
        expected_scifi.append(expected_book)
        assert list_scifi_books() == (False, expected_scifi)  # cache was invalidated by a new book
        assert list_scifi_books() == (True, expected_scifi)

        # Modify a sci-fi book
        modify_book(2, title='Caching is Easy')
        expected_book['title'] = 'Caching is Easy'
        assert list_scifi_books() == (False, expected_scifi)  # cache was invalidated by a modified book
        assert list_scifi_books() == (True, expected_scifi)

        # Modify another book
        add_other_book(category='tutorials')
        modify_book(3, title='Easy Gardening')
        assert list_scifi_books() == (True, expected_scifi)  # cache was NOT invalidated when other books were modified


    # Some imaginary books database
    books_db: MutableMapping[str, dict] = {}

    def list_scifi_books(category='sci-fi'):
        return list_books(category)

    def list_books(category: str):
        """ List books from a category

        Returns:
            (cache-hit, result)
        """
        # Attempt to get from cache
        try:
            return True, cache.get('books-sci-fi')
        except NotInCache:
            # Query the database
            books = [book for book in books_db.values()
                     if book['category'] == category]

            # 🪆 Cache, return
            cache.put(f'books-{category}', books,
                      # Every book is a dependency by id
                      *[dep.Id('book', book['id']) for book in books],
                      # The filtered list of books is itself a dependency.
                      # This condition() references a scope described using `@book_scopes.describes()`
                      # The resulting dependency is automatically invalidated using `book_scopes.object(book)`
                      *book_scopes.condition(category=category),
                      expires=600,
                      )
            return False, books

    def add_scifi_book(*, category='sci-fi', **fields):
        return add_book({'category': category, **fields})

    def add_other_book(*, category: str, **fields):
        return add_book({'category': category, **fields})

    def add_book(book: dict):
        # Save the book
        id = book['id'] = len(books_db) + 1  # auto-increment
        books_db[id] = book

        # 🪆 Invalidate caches: new book was added; invalidate lists
        # Generate dependencies that will invalidate some `book_scopes.condition(...)`
        book_scopes.invalidate_for(book, cache)

        # Done
        return book

    def modify_book(id: int, **fields):
        # Save the book
        book = books_db[id]
        book.update(fields)

        # 🪆 Invalidate caches: modified book
        cache.invalidate(dep.Id('book', id))

    main()

