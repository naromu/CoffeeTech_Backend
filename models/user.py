from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "user"

    user_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    verification_token = Column(String, unique=True)
    is_verified = Column(Boolean, default=False)
    session_token = Column(String, unique=True)

    # Métodos adicionales (como save, update, delete) no son necesarios con SQLAlchemy.
