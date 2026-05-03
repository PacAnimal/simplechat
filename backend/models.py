from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from .database import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), default="New Chat")
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    web_search_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan", order_by="Message.created_at")
    attachments = relationship("Attachment", back_populates="chat", cascade="all, delete-orphan")
    generated_images = relationship("GeneratedImage", back_populates="chat", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False, default="")
    tool_calls_json = Column(Text, nullable=True)
    tool_call_id = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=utcnow)

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
    created_at = Column(DateTime, default=utcnow)

    chat = relationship("Chat", back_populates="attachments")
    message = relationship("Message", back_populates="attachments")


class GeneratedImage(Base):
    __tablename__ = "generated_images"

    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    prompt = Column(Text, nullable=False)
    path = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=utcnow)

    chat = relationship("Chat", back_populates="generated_images")
    message = relationship("Message", back_populates="generated_images")
