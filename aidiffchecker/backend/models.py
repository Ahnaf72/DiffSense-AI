from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    full_name = Column(String(100))
    hashed_password = Column(String(255))
    role = Column(String(20), nullable=False)  # admin, teacher, student
    disabled = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

class ReferencePDF(Base):
    __tablename__ = "reference_pdfs"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255))
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    uploaded_at = Column(DateTime, server_default=func.now())