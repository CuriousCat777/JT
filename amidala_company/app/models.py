from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func

from .db import Base


class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    email = Column(String(300), nullable=False)
    organization = Column(String(300), nullable=True)
    message = Column(Text, nullable=True)
    cv_requested = Column(String(10), default="yes")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BookingRequest(Base):
    __tablename__ = "booking_requests"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    email = Column(String(300), nullable=False)
    requested_datetime = Column(String(100), nullable=False)
    topic = Column(String(300), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
