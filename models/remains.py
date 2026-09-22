from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, Numeric, String, func, text

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

    id = Column(Integer, primary_key=True)
    title = Column(String(120), nullable=False)
    description = Column(String(2000))
    status = Column(String(16), nullable=False, server_default="draft")
    image_url = Column(String(1024))
    video_url = Column(String(1024))
    analysis_time_days = Column(Integer)
    carbon_14_pmc = Column(Numeric(7, 3))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    creator_id = Column(Integer, ForeignKey("researchers.id", ondelete="RESTRICT"), nullable=False)
    published_at = Column(DateTime(timezone=True))
