"""Provide Flask routes for browsing books and adding library records."""

from datetime import date
import os

from flask import Flask, abort, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import SQLAlchemyError
from data_models import db, Author, Book

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or os.urandom(32)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(basedir, 'data/library.sqlite')}"
db.init_app(app)


@app.route('/')
def home():
    """Filter books by title and render them sorted by title or author."""
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
    """Display the author form or validate and save a submitted author."""
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
    """Display the book form or validate and save a book for an author."""
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


@app.route('/book/<int:book_id>/delete', methods=['POST'])
def delete_book(book_id):
    """Delete a book while keeping its author and redirect to the library."""
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
        db.create_all()
    app.run()
