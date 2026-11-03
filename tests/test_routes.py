"""Route tests with an in-memory database."""

import unittest
from unittest.mock import patch
from recommendations import RecommendationError, format_recommendation
from flask import Flask
from app import home, add_author, add_book, delete_book, book_detail, author_detail, rate_book, recommendations, delete_author
from data_models import db, Author, Book


class LibraryRoutesTest(unittest.TestCase):
    """Tests for library routes."""

    def setUp(self):
        """Set up an app with an empty test database."""
        self.app = Flask(__name__, template_folder='../templates')
        self.app.config.update(TESTING=True, SECRET_KEY='test', SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
        db.init_app(self.app)
        self.app.jinja_env.filters['recommendation_text'] = format_recommendation
        self.app.add_url_rule('/', 'home', home)
        self.app.add_url_rule('/add_author', 'add_author', add_author, methods=['GET', 'POST'])
        self.app.add_url_rule('/add_book', 'add_book', add_book, methods=['GET', 'POST'])
        self.app.add_url_rule('/book/<int:book_id>/delete', 'delete_book', delete_book, methods=['POST'])
        self.app.add_url_rule('/book/<int:book_id>', 'book_detail', book_detail)
        self.app.add_url_rule('/author/<int:author_id>', 'author_detail', author_detail)
        self.app.add_url_rule('/book/<int:book_id>/rate', 'rate_book', rate_book, methods=['POST'])
        self.app.add_url_rule('/recommendations', 'recommendations', recommendations, methods=['GET', 'POST'])
        self.app.add_url_rule('/author/<int:author_id>/delete', 'delete_author', delete_author, methods=['POST'])
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        """Clean up the test database and app context."""
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_empty_library_and_author_requirement(self):
        """Check empty pages and reject unknown authors."""
        self.assertIn('No books yet', self.client.get('/').text)
        self.assertIn('Please', self.client.get('/add_book').text)
        self.assertEqual(self.client.post('/add_book', data={'title': 'Book', 'author_id': '999'}).status_code, 400)
        self.assertEqual(db.session.query(Book).count(), 0)

    def test_ratings(self):
        """Check saving, validating, and clearing ratings."""
        book = Book(title='Rated Book', author=Author(name='Test'))
        db.session.add(book)
        db.session.commit()
        url = f'/book/{book.id}/rate'
        for score in ('1', '10'):
            response = self.client.post(url, data={'rating': score}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(db.session.get(Book, book.id).rating, int(score))
            self.assertIn(f'Rated {score} / 10', self.client.get('/').text)
        for score in ('0', '11', '1.5', 'invalid'):
            self.assertEqual(self.client.post(url, data={'rating': score}).status_code, 400)
            self.assertEqual(db.session.get(Book, book.id).rating, 10)
        self.client.post(url, data={'rating': ''})
        self.assertIsNone(db.session.get(Book, book.id).rating)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post('/book/99999/rate').status_code, 404)

    @patch('app.recommend_books')
    def test_recommendations(self, provider):
        """Check when recommendations run and how output is escaped."""
        self.assertEqual(self.client.get('/recommendations').status_code, 200)
        self.assertEqual(self.client.post('/recommendations').status_code, 400)
        provider.assert_not_called()
        book = Book(title='A Book', author=Author(name='An Author'), rating=9)
        db.session.add(book)
        db.session.commit()
        provider.return_value = '<script>unsafe</script> Try another book.'
        response = self.client.post('/recommendations')
        self.assertEqual(response.status_code, 200)
        self.assertIn('&lt;script&gt;', response.text)
        self.assertEqual(provider.call_args.args[0][0].rating, 9)
        provider.side_effect = RecommendationError('Please try again later.')
        response = self.client.post('/recommendations')
        self.assertEqual(response.status_code, 503)
        self.assertIn('Please try again later.', response.text)

    def test_detail_pages(self):
        """Check detail pages, links, and missing records."""
        author = Author(name='Detail Author')
        other = Author(name='Other Author')
        book = Book(title='Detail Book', isbn='9780140328721',
                    publication_year=2001, author=author)
        db.session.add_all([book, other])
        db.session.commit()
        book_url = f'/book/{book.id}'
        author_url = f'/author/{author.id}'
        home_page = self.client.get('/').text
        self.assertIn(f'href="{book_url}"', home_page)
        self.assertIn(f'href="{author_url}"', home_page)
        response = self.client.get(book_url)
        self.assertEqual(response.status_code, 200)
        for value in ('Detail Book', 'Detail Author', '2001', '9780140328721'):
            self.assertIn(value, response.text)
        self.assertIn(f'href="{author_url}"', response.text)
        response = self.client.get(author_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'href="{book_url}"', response.text)
        self.assertIn('Unknown', response.text)
        self.assertIn('Not recorded', response.text)
        other_page = self.client.get(f'/author/{other.id}').text
        self.assertIn('No books by this author', other_page)
        self.assertNotIn('Detail Book', other_page)
        book.isbn = None
        book.publication_year = None
        db.session.commit()
        self.assertIn('Not provided', self.client.get(book_url).text)
        for url in ('/book/99999', '/author/99999'):
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_delete_author(self):
        """Delete the author's books without affecting other authors."""
        author = Author(name='Delete Me')
        other = Author(name='Keep Me')
        first = Book(title='First', author=author)
        second = Book(title='Second', author=author)
        kept = Book(title='Keep This', author=other)
        db.session.add_all([first, second, kept])
        db.session.commit()
        author_id, other_id = author.id, other.id
        first_id, second_id, kept_id = first.id, second.id, kept.id
        url = f'/author/{author_id}/delete'
        self.assertIn(f'action="{url}"', self.client.get('/').text)
        self.assertIn(f'action="{url}"', self.client.get(f'/author/{author_id}').text)
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/')
        self.assertIn('all their books successfully deleted', self.client.get('/').text)
        self.assertIsNone(db.session.get(Author, author_id))
        self.assertIsNone(db.session.get(Book, first_id))
        self.assertIsNone(db.session.get(Book, second_id))
        self.assertIsNotNone(db.session.get(Book, kept_id))
        self.assertIsNotNone(db.session.get(Author, other_id))
        self.assertEqual(self.client.post(url).status_code, 404)
        empty = Author(name='No Books')
        db.session.add(empty)
        db.session.commit()
        empty_id = empty.id
        self.assertEqual(self.client.post(f'/author/{empty_id}/delete').status_code, 302)
        self.assertIsNone(db.session.get(Author, empty_id))

    def test_delete_book(self):
        """Check book deletion and keep the author."""
        author = Author(name='Test Author')
        first = Book(title='First Book', author=author)
        second = Book(title='Second Book', author=author)
        db.session.add_all([first, second])
        db.session.commit()
        first_id, second_id, author_id = first.id, second.id, author.id
        url = f'/book/{first_id}/delete'
        self.assertIn(f'action="{url}" method="post"', self.client.get('/').text)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertIsNotNone(db.session.get(Book, first_id))
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/')
        page = self.client.get('/').text
        self.assertIn('Book "First Book" successfully deleted.'.replace('"', '&#34;'), page)
        self.assertNotIn('>First Book</a></h2>', page)
        self.assertIn('>Second Book</a></h2>', page)
        self.assertIsNone(db.session.get(Book, first_id))
        self.assertEqual(self.client.post(url).status_code, 404)
        self.client.post(f'/book/{second_id}/delete')
        self.assertEqual(db.session.query(Book).count(), 0)
        self.assertIsNotNone(db.session.get(Author, author_id))

    def test_title_search(self):
        """Check search phrases, sorting, and special characters."""
        alpha = Author(name='Alpha')
        zulu = Author(name='Zulu')
        db.session.add_all([
            Book(title='The River Road', author=alpha),
            Book(title='A River Story', author=zulu),
            Book(title='100% Python_Examples', author=alpha),
        ])
        db.session.commit()
        page = self.client.get('/', query_string={'search': ' RIVER ', 'sort': 'author'}).text
        self.assertIn('>The River Road</a></h2>', page)
        self.assertIn('>A River Story</a></h2>', page)
        self.assertNotIn('>100% Python_Examples</a></h2>', page)
        self.assertLess(page.index('>The River'), page.index('>A River'))
        self.assertIn('value="RIVER"', page)
        phrase = self.client.get('/', query_string={'search': 'river road'}).text
        self.assertIn('>The River Road</a></h2>', phrase)
        self.assertNotIn('>A River Story</a></h2>', phrase)
        missing = self.client.get('/', query_string={'search': 'missing'}).text
        self.assertIn('No books match your search', missing)
        self.assertNotIn('No books yet', missing)
        for search in ('%', '_'):
            page = self.client.get('/', query_string={'search': search}).text
            self.assertIn('>100% Python_Examples</a></h2>', page)
            self.assertNotIn('>The River Road</a></h2>', page)
        self.assertEqual(self.client.get('/?search=+++').text.count('<article>'), 3)

    def test_author_validation_and_success(self):
        """Check author validation and saving."""
        for data in ({'name': ' '}, {'name': 'Test', 'birthdate': 'bad'}, {'name': 'Test', 'birthdate': '2000-01-01', 'date_of_death': '1999-01-01'}):
            self.assertEqual(self.client.post('/add_author', data=data).status_code, 400)
        self.assertEqual(db.session.query(Author).count(), 0)
        response = self.client.post('/add_author', data={'name': 'Test', 'birthdate': '1900-01-01'}, follow_redirects=True)
        self.assertIn('successfully added', response.text)
        self.assertEqual(db.session.query(Author).one().birth_date.isoformat(), '1900-01-01')
        self.client.get('/add_author')
        self.assertEqual(db.session.query(Author).count(), 1)

    def test_books_sorting_and_validation(self):
        """Check book saving, sorting, covers, and validation."""
        a = Author(name='Alpha')
        z = Author(name='Zulu')
        db.session.add_all([a, z])
        db.session.commit()
        for title, author in [('Zebra', a), ('Apple', z)]:
            response = self.client.post('/add_book', data={'title': title, 'author_id': str(author.id), 'publication_year': '2001', 'isbn': '978-0140328721'}, follow_redirects=True)
            self.assertIn('successfully added', response.text)
        title_page = self.client.get('/?sort=title').text
        author_page = self.client.get('/?sort=author').text
        self.assertLess(title_page.index('>Apple'), title_page.index('>Zebra'))
        self.assertLess(author_page.index('>Zebra'), author_page.index('>Apple'))
        self.assertIn('Zulu', title_page)
        self.assertIn('covers.openlibrary.org/b/isbn/9780140328721-M.jpg', title_page)
        self.assertEqual(self.client.get('/?sort=invalid').status_code, 200)
        for changes in ({'title': ' '}, {'author_id': '999'}, {'author_id': 'abc'}, {'publication_year': 'bad'}, {'publication_year': '0'}, {'isbn': 'bad'}):
            data = {'title': 'Invalid', 'author_id': str(a.id)}
            data.update(changes)
            self.assertEqual(self.client.post('/add_book', data=data).status_code, 400)
        self.assertEqual(db.session.query(Book).count(), 2)


if __name__ == '__main__':
    unittest.main()
