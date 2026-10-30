"""Define the author and book models for the library database."""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Author(db.Model):
    """Store an author's name and optional birth and death dates."""

    __tablename__ = 'authors'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String, nullable=False)
    birth_date = db.Column(db.Date)
    date_of_death = db.Column(db.Date)

    def __repr__(self) -> str:
        """Return the author's name for debugging output."""
        return self.name

    def __str__(self) -> str:
        """Return the author's name as a readable string."""
        return self.name


class Book(db.Model):
    """Store a book's bibliographic details and associated author."""

    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    isbn = db.Column(db.String)
    title = db.Column(db.String, nullable=False)
    publication_year = db.Column(db.Integer)
    author_id = db.Column(db.Integer, db.ForeignKey('authors.id'), nullable=False)
    author = db.relationship('Author', backref='books')

    def __repr__(self) -> str:
        """Return the book's title for debugging output."""
        return self.title

    def __str__(self) -> str:
        """Return the book's title as a readable string."""
        return self.title
