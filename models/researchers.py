from sqlalchemy import Column, Integer, String

from db.base import Base


class Researchers(Base):
    __tablename__ = "researchers"

    id = Column(Integer, primary_key=True)
    username = Column(String(80), nullable=False, unique=True)
    full_name = Column(String(160), nullable=False)
