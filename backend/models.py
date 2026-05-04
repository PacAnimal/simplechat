from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """DateTime that always returns timezone-aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    password_hash = Column(String(255), nullable=False)
    avatar = Column(Integer, nullable=False, default=0)
    avatar_color = Column(String(20), nullable=True)
    created_at = Column(UTCDateTime, default=utcnow)
    token_invalidated_at = Column(UTCDateTime, nullable=True)

    chats = relationship("Chat", back_populates="profile", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("name", name="uq_profiles_name"),)


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer, ForeignKey("profiles.id"), nullable=False)
    title = Column(String(255), default="New Chat")
    title_is_default = Column(Boolean, default=True, nullable=False)
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    web_search_enabled = Column(Boolean, default=False)
    created_at = Column(UTCDateTime, default=utcnow)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow)
    discarded_at = Column(UTCDateTime, nullable=True)

    profile = relationship("Profile", back_populates="chats")
    messages = relationship(
        "Message",
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    attachments = relationship(
        "Attachment", back_populates="chat", cascade="all, delete-orphan"
    )
    generated_images = relationship(
        "GeneratedImage", back_populates="chat", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False, default="")
    thinking = Column(Text, nullable=True)
    created_at = Column(UTCDateTime, default=utcnow)

    chat = relationship("Chat", back_populates="messages")
    attachments = relationship("Attachment", back_populates="message")
    generated_images = relationship("GeneratedImage", back_populates="message")


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    path = Column(String(500), nullable=False)
    size = Column(BigInteger, nullable=False)
    created_at = Column(UTCDateTime, default=utcnow)

    chat = relationship("Chat", back_populates="attachments")
    message = relationship("Message", back_populates="attachments")


class GeneratedImage(Base):
    __tablename__ = "generated_images"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    prompt = Column(Text, nullable=False)
    path = Column(String(500), nullable=False)
    created_at = Column(UTCDateTime, default=utcnow)

    chat = relationship("Chat", back_populates="generated_images")
    message = relationship("Message", back_populates="generated_images")
