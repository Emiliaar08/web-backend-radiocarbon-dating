from alembic import op
import sqlalchemy as sa

revision = "0001_remains"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "researchers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False, unique=True),
        sa.Column("full_name", sa.String(160), nullable=False),
    )
    op.create_table(
        "remains",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.String(2000)),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("image_url", sa.String(1024)),
        sa.Column("video_url", sa.String(1024)),
        sa.Column("analysis_time_days", sa.Integer()),
        sa.Column("carbon_14_pmc", sa.Numeric(7, 3)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("creator_id", sa.Integer(), sa.ForeignKey("researchers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('draft', 'published', 'deleted')", name="ck_remains_status"),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_remains_title"),
        sa.CheckConstraint("analysis_time_days > 0", name="ck_remains_analysis_time"),
        sa.CheckConstraint("carbon_14_pmc BETWEEN 0 AND 200", name="ck_remains_carbon"),
        sa.CheckConstraint(
            "status != 'published' OR (description IS NOT NULL AND length(trim(description)) > 0 "
            "AND analysis_time_days IS NOT NULL AND carbon_14_pmc IS NOT NULL AND published_at IS NOT NULL)",
            name="ck_remains_publication",
        ),
    )
    op.create_index("uq_remains_creator_draft", "remains", ["creator_id"], unique=True, postgresql_where=sa.text("status = 'draft'"))
    op.create_table(
        "remains_likes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("researcher_id", sa.Integer(), sa.ForeignKey("researchers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("remains_id", sa.Integer(), sa.ForeignKey("remains.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("researcher_id", "remains_id", name="uq_remains_like"),
    )
    op.create_index("ix_remains_likes_remains_id", "remains_likes", ["remains_id"])


def downgrade():
    op.drop_table("remains_likes")
    op.drop_index("uq_remains_creator_draft", table_name="remains")
    op.drop_table("remains")
    op.drop_table("researchers")
