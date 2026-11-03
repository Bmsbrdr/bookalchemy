"""Library routes."""

from datetime import date
import os

from flask import Flask, abort, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from data_models import db, Author, Book
from recommendations import RecommendationError, format_recommendation, recommend_books

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or os.urandom(32)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'data/library.sqlite')}"
db.init_app(app)
app.jinja_env.filters['recommendation_text'] = format_recommendation


def initialize_database():
    """Create tables and add ratings to older databases."""
    db.create_all()
    columns = {column['name'] for column in inspect(db.engine).get_columns('books')}
    if 'rating' not in columns:
        with db.engine.begin() as connection:
            connection.execute(text(
                'ALTER TABLE books ADD COLUMN rating INTEGER '
                'CHECK (rating BETWEEN 1 AND 10)'
            ))


@app.route('/')
def home():
    """Show books with title search and sorting."""
    search = request.args.get('search', '').strip()
    sort = request.args.get('sort', 'title')
    if sort not in ('title', 'author'):
        sort = 'title'
    order = db.func.lower(Author.name) if sort == 'author' else db.func.lower(Book.title)
    query = db.select(Book).join(Author).options(db.joinedload(Book.author))
    if search:
        query = query.where(Book.title.icontains(search, autoescape=True))
    books = db.session.execute(
        query.order_by(order, db.func.lower(Book.title), Book.id)
    ).scalars().all()
    return render_template('home.html', books=books, sort=sort, search=search)


@app.route('/add_author', methods=['GET', 'POST'])
def add_author():
    """Show the author form and save valid submissions."""
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            birth = request.form.get('birthdate', '').strip()
            death = request.form.get('date_of_death', '').strip()
            birth_date = date.fromisoformat(birth) if birth else None
            date_of_death = date.fromisoformat(death) if death else None
            if not name:
                raise ValueError('Please enter an author name.')
            if birth_date and date_of_death and date_of_death < birth_date:
                raise ValueError('The date of death cannot be before the date of birth.')
            db.session.add(Author(name=name, birth_date=birth_date, date_of_death=date_of_death))
            db.session.commit()
        except ValueError as error:
            return render_template('add_author.html', error=str(error)), 400
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception('Could not save author')
            return render_template('add_author.html', error='Could not save. Please try again.'), 500
        flash(f'Author "{name}" successfully added.')
        return redirect(url_for('add_author'))
    return render_template('add_author.html')


@app.route('/add_book', methods=['GET', 'POST'])
def add_book():
    """Show the book form and save valid submissions."""
    authors = db.session.execute(db.select(Author).order_by(db.func.lower(Author.name))).scalars().all()
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            isbn = request.form.get('isbn', '').strip().replace('-', '').replace(' ', '').upper()
            year_text = request.form.get('publication_year', '').strip()
            year = int(year_text) if year_text else None
            author_id = int(request.form.get('author_id', ''))
            if not title:
                raise ValueError('Please enter a book title.')
            if year is not None and not 1 <= year <= 9999:
                raise ValueError('The publication year must be between 1 and 9999.')
            if isbn and not (len(isbn) == 13 and isbn.isdigit() or len(isbn) == 10 and isbn[:9].isdigit() and (isbn[-1].isdigit() or isbn[-1] == 'X')):
                raise ValueError('Please enter an ISBN with 10 or 13 characters.')
            if db.session.get(Author, author_id) is None:
                raise ValueError('Please select an existing author.')
            db.session.add(Book(title=title, isbn=isbn or None, publication_year=year, author_id=author_id))
            db.session.commit()
        except ValueError as error:
            return render_template('add_book.html', authors=authors, error=str(error)), 400
        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception('Could not save book')
            return render_template('add_book.html', authors=authors, error='Could not save. Please try again.'), 500
        flash(f'Book "{title}" successfully added.')
        return redirect(url_for('add_book'))
    return render_template('add_book.html', authors=authors)


@app.route('/book/<int:book_id>')
def book_detail(book_id):
    """Show book details; return 404 if missing."""
    book = db.get_or_404(Book, book_id)
    return render_template('book_detail.html', book=book)


@app.route('/author/<int:author_id>')
def author_detail(author_id):
    """Show an author's details and books; return 404 if missing."""
    author = db.get_or_404(Author, author_id)
    books = db.session.execute(
        db.select(Book).where(Book.author_id == author.id)
        .order_by(db.func.lower(Book.title), Book.id)
    ).scalars().all()
    return render_template('author_detail.html', author=author, books=books)


@app.route('/book/<int:book_id>/rate', methods=['POST'])
def rate_book(book_id):
    """Save a rating from 1 to 10, or clear it."""
    book = db.get_or_404(Book, book_id)
    raw_rating = request.form.get('rating', '').strip()
    try:
        rating = int(raw_rating) if raw_rating else None
        if rating is not None and not 1 <= rating <= 10:
            raise ValueError
    except ValueError:
        return render_template('book_detail.html', book=book,
                               error='Please choose a whole-number rating from 1 to 10.'), 400
    try:
        book.rating = rating
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Could not save book rating')
        return render_template('book_detail.html', book=book,
                               error='Could not save your rating. Please try again.'), 500
    flash('Rating saved.' if rating is not None else 'Rating cleared.')
    return redirect(url_for('book_detail', book_id=book.id))


@app.route('/recommendations', methods=['GET', 'POST'])
def recommendations():
    """Request a recommendation when the form is submitted."""
    books = db.session.execute(
        db.select(Book).options(db.joinedload(Book.author)).order_by(Book.id)
    ).scalars().all()
    result = None
    error = None
    status = 200
    if request.method == 'POST':
        if not books:
            error = 'Add some books to your library before requesting a recommendation.'
            status = 400
        else:
            try:
                result = recommend_books(books)
            except RecommendationError as exception:
                error = str(exception)
                status = 503
    return render_template('recommendations.html', books=books,
                           recommendation=result, error=error), status


@app.route('/author/<int:author_id>/delete', methods=['POST'])
def delete_author(author_id):
    """Delete an author and their books, then return to the library."""
    author = db.get_or_404(Author, author_id)
    name = author.name
    try:
        db.session.delete(author)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Could not delete author')
        flash('Could not delete the author. Please try again.')
    else:
        flash(f'Author "{name}" and all their books successfully deleted.')
    return redirect(url_for('home'))


@app.route('/book/<int:book_id>/delete', methods=['POST'])
def delete_book(book_id):
    """Delete the book, keep its author, and return to the library."""
    book = db.session.get(Book, book_id)
    if book is None:
        abort(404)
    title = book.title
    try:
        db.session.delete(book)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception('Could not delete book')
        flash('Could not delete the book. Please try again.')
    else:
        flash(f'Book "{title}" successfully deleted.')
    return redirect(url_for('home'))


if __name__ == '__main__':
    with app.app_context():
        initialize_database()
    app.run()
