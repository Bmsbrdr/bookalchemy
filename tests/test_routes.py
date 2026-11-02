"""Verify library routes using an isolated in-memory database."""

import unittest
from flask import Flask
from app import home, add_author, add_book
from data_models import db, Author, Book


class LibraryRoutesTest(unittest.TestCase):
    """Test form validation, record creation, and library sorting."""

    def setUp(self):
        """Create a test application with empty author and book tables."""
        self.app = Flask(__name__, template_folder='../templates')
        self.app.config.update(TESTING=True, SECRET_KEY='test', SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
        db.init_app(self.app)
        self.app.add_url_rule('/', 'home', home)
        self.app.add_url_rule('/add_author', 'add_author', add_author, methods=['GET', 'POST'])
        self.app.add_url_rule('/add_book', 'add_book', add_book, methods=['GET', 'POST'])
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        """Remove the test session, tables, and application context."""
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_empty_library_and_author_requirement(self):
        """Verify empty pages and reject books without an existing author."""
        self.assertIn('No books yet', self.client.get('/').text)
        self.assertIn('Please', self.client.get('/add_book').text)
        self.assertEqual(self.client.post('/add_book', data={'title': 'Book', 'author_id': '999'}).status_code, 400)
        self.assertEqual(db.session.query(Book).count(), 0)

    def test_title_search(self):
        """Verify phrase matching, sorting, empty queries, and literal wildcards."""
        alpha = Author(name='Alpha')
        zulu = Author(name='Zulu')
        db.session.add_all([
            Book(title='The River Road', author=alpha),
            Book(title='A River Story', author=zulu),
            Book(title='100% Python_Examples', author=alpha),
        ])
        db.session.commit()
        page = self.client.get('/', query_string={'search': ' RIVER ', 'sort': 'author'}).text
        self.assertIn('<h2>The River Road</h2>', page)
        self.assertIn('<h2>A River Story</h2>', page)
        self.assertNotIn('<h2>100% Python_Examples</h2>', page)
        self.assertLess(page.index('<h2>The River'), page.index('<h2>A River'))
        self.assertIn('value="RIVER"', page)
        phrase = self.client.get('/', query_string={'search': 'river road'}).text
        self.assertIn('<h2>The River Road</h2>', phrase)
        self.assertNotIn('<h2>A River Story</h2>', phrase)
        missing = self.client.get('/', query_string={'search': 'missing'}).text
        self.assertIn('No books match your search', missing)
        self.assertNotIn('No books yet', missing)
        for search in ('%', '_'):
            page = self.client.get('/', query_string={'search': search}).text
            self.assertIn('<h2>100% Python_Examples</h2>', page)
            self.assertNotIn('<h2>The River Road</h2>', page)
        self.assertEqual(self.client.get('/?search=+++').text.count('<article>'), 3)

    def test_author_validation_and_success(self):
        """Reject invalid author data and confirm a valid author is saved."""
        for data in ({'name': ' '}, {'name': 'Test', 'birthdate': 'bad'}, {'name': 'Test', 'birthdate': '2000-01-01', 'date_of_death': '1999-01-01'}):
            self.assertEqual(self.client.post('/add_author', data=data).status_code, 400)
        self.assertEqual(db.session.query(Author).count(), 0)
        response = self.client.post('/add_author', data={'name': 'Test', 'birthdate': '1900-01-01'}, follow_redirects=True)
        self.assertIn('successfully added', response.text)
        self.assertEqual(db.session.query(Author).one().birth_date.isoformat(), '1900-01-01')
        self.client.get('/add_author')
        self.assertEqual(db.session.query(Author).count(), 1)

    def test_books_sorting_and_validation(self):
        """Verify book creation, sorting, covers, and invalid input handling."""
        a = Author(name='Alpha')
        z = Author(name='Zulu')
        db.session.add_all([a, z])
        db.session.commit()
        for title, author in [('Zebra', a), ('Apple', z)]:
            response = self.client.post('/add_book', data={'title': title, 'author_id': str(author.id), 'publication_year': '2001', 'isbn': '978-0140328721'}, follow_redirects=True)
            self.assertIn('successfully added', response.text)
        title_page = self.client.get('/?sort=title').text
        author_page = self.client.get('/?sort=author').text
        self.assertLess(title_page.index('<h2>Apple'), title_page.index('<h2>Zebra'))
        self.assertLess(author_page.index('<h2>Zebra'), author_page.index('<h2>Apple'))
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
