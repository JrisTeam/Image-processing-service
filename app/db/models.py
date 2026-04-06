from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from app.db.base import Base


def _uuid() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=_utcnow)

    images = relationship("ImageRecord", back_populates="owner")


class ImageRecord(Base):
    __tablename__ = "images"

    id = Column(String(36), primary_key=True, default=_uuid)
    owner_id = Column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    storage_key = Column(String, nullable=False)
    storage_url = Column(String, nullable=False)
    format = Column(String, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    uploaded_at = Column(DateTime, default=_utcnow)

    owner = relationship("User", back_populates="images")
    transformations = relationship("TransformationRecord", back_populates="source_image")


class TransformationRecord(Base):
    __tablename__ = "transformations"

    id = Column(String(36), primary_key=True, default=_uuid)
    source_image_id = Column(String(36), ForeignKey("images.id"), index=True, nullable=False)
    pipeline_hash = Column(String, nullable=False)
    operations = Column(JSON, nullable=False)
    storage_key = Column(String, nullable=False)
    storage_url = Column(String, nullable=False)
    created_at = Column(DateTime, default=_utcnow)

    source_image = relationship("ImageRecord", back_populates="transformations")
