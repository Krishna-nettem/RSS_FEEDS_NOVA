from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, Column, String, ForeignKey, Index, DateTime, func
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
from contextlib import contextmanager
import os
import uuid
from datetime import datetime
from typing import Generator, List, Optional, Dict, Any

# =====================
# Database Setup
# =====================
# Create engine with proper connection settings
DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Check connection before using from pool
    pool_size=5,         # Reasonable pool size for school project
    max_overflow=10,     # Allow up to 10 connections beyond pool_size
    pool_recycle=3600,   # Recycle connections after 1 hour
    echo=False           # Set to True to see SQL queries in console during development
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for declarative models
Base = declarative_base()

# =====================
# Database Session Context Manager
# =====================
@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for database sessions"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# =====================
# FastAPI Dependency for Database Access
# =====================
def get_db() -> Generator[Session, None, None]:
    """Dependency for getting DB sessions in FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =====================
# Model Mixins
# =====================
class TimestampMixin:
    """Mixin to add created_at and updated_at timestamps"""
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

# =====================
# ORM Models
# =====================
class User(Base):
    __tablename__ = "users"
    
    email = Column(String(255), primary_key=True, index=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    
    # Define relationships
    arxiv_topics = relationship("UserArxivTopic", back_populates="user", cascade="all, delete-orphan")
    book_categories = relationship("UserBookCategory", back_populates="user", cascade="all, delete-orphan")
    favorites = relationship("Favorite", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User {self.email}>"
    
    @classmethod
    def create(cls, db: Session, email: str) -> "User":
        """Create a new user"""
        user = cls(email=email)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    
    @classmethod
    def get_by_email(cls, db: Session, email: str) -> Optional["User"]:
        """Get a user by email"""
        return db.query(cls).filter(cls.email == email).first()
    
    def get_arxiv_topics(self, db: Session) -> List[str]:
        """Get list of arxiv topic IDs for this user"""
        return [topic.arxiv_topic_id for topic in self.arxiv_topics]
    
    def get_book_categories(self, db: Session) -> List[str]:
        """Get list of book category IDs for this user"""
        return [cat.book_category_id for cat in self.book_categories]


class UserArxivTopic(Base):
    __tablename__ = "user_arxiv_topics"
    
    # Use composite primary key
    user_email = Column(String(255), ForeignKey("users.email", ondelete="CASCADE"), primary_key=True)
    arxiv_topic_id = Column(String(50), primary_key=True)
    
    # Define relationship back to user
    user = relationship("User", back_populates="arxiv_topics")
    
    def __repr__(self):
        return f"<UserArxivTopic {self.user_email}: {self.arxiv_topic_id}>"
    
    @classmethod
    def add_topics_for_user(cls, db: Session, user_email: str, topic_ids: List[str]) -> None:
        """Add multiple topics for a user, replacing existing ones"""
        # Delete existing topics
        db.query(cls).filter(cls.user_email == user_email).delete()
        
        # Add new topics
        for topic_id in topic_ids:
            db.add(cls(user_email=user_email, arxiv_topic_id=topic_id))
        
        db.commit()


class UserBookCategory(Base):
    __tablename__ = "user_book_categories"
    
    # Use composite primary key
    user_email = Column(String(255), ForeignKey("users.email", ondelete="CASCADE"), primary_key=True)
    book_category_id = Column(String(50), primary_key=True)
    
    # Define relationship back to user
    user = relationship("User", back_populates="book_categories")
    
    def __repr__(self):
        return f"<UserBookCategory {self.user_email}: {self.book_category_id}>"
    
    @classmethod
    def add_categories_for_user(cls, db: Session, user_email: str, category_ids: List[str]) -> None:
        """Add multiple categories for a user, replacing existing ones"""
        # Delete existing categories
        db.query(cls).filter(cls.user_email == user_email).delete()
        
        # Add new categories
        for cat_id in category_ids:
            db.add(cls(user_email=user_email, book_category_id=cat_id))
        
        db.commit()


class Favorite(Base, TimestampMixin):
    __tablename__ = "favourites"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_email = Column(String(255), ForeignKey("users.email", ondelete="CASCADE"), index=True)
    title = Column(String(500), nullable=False)
    type = Column(String(20), nullable=False)  # 'arxiv' or 'book'
    link = Column(String(1000), nullable=False)
    date_published = Column(String(30))
    
    # Define relationship back to user
    user = relationship("User", back_populates="favorites")
    
    def __repr__(self):
        return f"<Favorite {self.id}: {self.title[:30]}...>"
    
    @classmethod
    def add_favorite(cls, db: Session, user_email: str, title: str, 
                    type_: str, link: str, date_published: str) -> "Favorite":
        """Add a favorite for a user"""
        # Check if already exists
        existing = db.query(cls).filter(
            cls.user_email == user_email,
            cls.title == title,
            cls.link == link
        ).first()
        
        if existing:
            return existing
            
        # Create new favorite
        favorite = cls(
            user_email=user_email,
            title=title,
            type=type_,
            link=link,
            date_published=date_published
        )
        
        db.add(favorite)
        db.commit()
        db.refresh(favorite)
        return favorite
    
    @classmethod
    def remove_favorite(cls, db: Session, fav_id: str, user_email: str) -> bool:
        """Remove a favorite for a user"""
        result = db.query(cls).filter(
            cls.id == fav_id,
            cls.user_email == user_email
        ).delete()
        
        db.commit()
        return result > 0


# Create tables
Base.metadata.create_all(bind=engine)

# =====================
# Legacy Support (for backward compatibility with your existing code)
# =====================
# These variables allow your existing code to work with minimal changes.
# They enable SQLAlchemy Core-style queries.
users = User.__table__
user_arxiv_topics = UserArxivTopic.__table__
user_book_categories = UserBookCategory.__table__
favourites = Favorite.__table__
