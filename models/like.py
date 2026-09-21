from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class RemainsLike(Base):
    __tablename__ = "remains_likes"
    __table_args__ = (UniqueConstraint("researcher_id", "remains_id", name="uq_remains_like"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    researcher_id: Mapped[int] = mapped_column(ForeignKey("researchers.id", ondelete="RESTRICT"))
    remains_id: Mapped[int] = mapped_column(ForeignKey("remains.id", ondelete="RESTRICT"), index=True)
