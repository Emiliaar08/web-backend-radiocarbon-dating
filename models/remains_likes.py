from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint

from db.base import Base


class RemainsLikes(Base):
    __tablename__ = "remains_likes"
    __table_args__ = (UniqueConstraint("researcher_id", "remains_id", name="uq_remains_like"),)

    id = Column(Integer, primary_key=True)
    researcher_id = Column(Integer, ForeignKey("researchers.id", ondelete="RESTRICT"), nullable=False)
    remains_id = Column(Integer, ForeignKey("remains.id", ondelete="RESTRICT"), nullable=False, index=True)
