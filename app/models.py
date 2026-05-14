from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, String, Text, Index,
)

from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String, unique=True, index=True, nullable=False)
    source = Column(String, nullable=False)  # yad2 | madlan
    url = Column(String)
    title = Column(String)
    price = Column(Integer, index=True)
    city = Column(String, index=True)
    city_code = Column(String)
    neighborhood = Column(String)
    address = Column(String)
    size_sqm = Column(Float)
    rooms = Column(Float)
    floor = Column(Integer)
    total_floors = Column(Integer)
    has_parking = Column(Boolean)
    has_elevator = Column(Boolean)
    image_url = Column(String)
    property_type = Column(String)
    description = Column(Text)

    first_seen = Column(DateTime, default=_utcnow)
    last_seen = Column(DateTime, default=_utcnow)
    status = Column(String, default="new")  # new | saved | not_interested

    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_city_price", "city", "price"),
        Index("ix_neighborhood", "neighborhood"),
    )


class ScrapeLog(Base):
    __tablename__ = "scrape_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, default=_utcnow)
    finished_at = Column(DateTime)
    source = Column(String)
    status = Column(String, default="running")  # running | success | error
    listings_found = Column(Integer, default=0)
    listings_new = Column(Integer, default=0)
    error_message = Column(Text)
