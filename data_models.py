"""Author and book models."""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Author(db.Model):
    """An author and their life dates."""

    __tablename__ = 'authors'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String, nullable=False)
    birth_date = db.Column(db.Date)
    date_of_death = db.Column(db.Date)
    books = db.relationship(
        'Book', back_populates='author', cascade='all, delete-orphan'
    )

    def __repr__(self) -> str:
        """Return the author's name for debugging."""
        return self.name

    def __str__(self) -> str:
        """Return the author's name."""
        return self.name


class Book(db.Model):
    """A book, its author, and its rating."""

    __tablename__ = 'books'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    isbn = db.Column(db.String)
    title = db.Column(db.String, nullable=False)
    publication_year = db.Column(db.Integer)
    rating = db.Column(db.Integer)
    __table_args__ = (
        db.CheckConstraint('rating BETWEEN 1 AND 10', name='valid_book_rating'),
    )
    author_id = db.Column(db.Integer, db.ForeignKey('authors.id'), nullable=False)
    author = db.relationship('Author', back_populates='books')

    def __repr__(self) -> str:
        """Return the title for debugging."""
        return self.title

    def __str__(self) -> str:
        """Return the book title."""
        return self.title
