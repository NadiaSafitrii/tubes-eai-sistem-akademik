from sqlalchemy import Column, Integer, String, ForeignKey
from database import Base

class Student(Base):
    __tablename__ = "students"

    student_id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False, index=True)
    semester = Column(Integer, nullable=False)
    status = Column(String(20), default="inactive", nullable=False)

class Class(Base):
    __tablename__ = "classes"

    class_id = Column(String(50), primary_key=True, index=True)
    name = Column(String(100), nullable=False)

class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    student_id = Column(String(50), ForeignKey("students.student_id", ondelete="CASCADE"), nullable=False)
    class_id = Column(String(50), ForeignKey("classes.class_id", ondelete="CASCADE"), nullable=False)

