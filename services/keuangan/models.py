# SQLAlchemy Models for Keuangan Service
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime
from database import Base

class Bill(Base):
    __tablename__ = "bills"

    bill_id = Column(String(50), primary_key=True, index=True)
    student_id = Column(String(50), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    semester = Column(Integer, nullable=False)
    status = Column(String(20), default="unpaid", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

