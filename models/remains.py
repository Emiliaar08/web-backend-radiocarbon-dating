from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Remains(Base):
    __tablename__ = "remains"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published', 'deleted')", name="ck_remains_status"),
        CheckConstraint("length(trim(title)) > 0", name="ck_remains_title"),
        CheckConstraint("analysis_time_days > 0", name="ck_remains_analysis_time"),
        CheckConstraint("carbon_14_pmc BETWEEN 0 AND 200", name="ck_remains_carbon"),
        CheckConstraint(
            "status != 'published' OR (description IS NOT NULL AND length(trim(description)) > 0 "
            "AND analysis_time_days IS NOT NULL AND carbon_14_pmc IS NOT NULL AND published_at IS NOT NULL)",
            name="ck_remains_publication",
        ),
        Index("uq_remains_creator_draft", "creator_id", unique=True, postgresql_where=text("status = 'draft'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(16), server_default="draft")
    image_url: Mapped[str | None] = mapped_column(String(1024))
    video_url: Mapped[str | None] = mapped_column(String(1024))
    analysis_time_days: Mapped[int | None]
    carbon_14_pmc: Mapped[Decimal | None] = mapped_column(Numeric(7, 3))
    carbon_14_sample: Mapped[str | None] = mapped_column(String(160))
    carbon_14_source: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    creator_id: Mapped[int] = mapped_column(ForeignKey("researchers.id", ondelete="RESTRICT"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
