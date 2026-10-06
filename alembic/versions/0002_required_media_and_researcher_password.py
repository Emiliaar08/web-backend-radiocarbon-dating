from alembic import op
import sqlalchemy as sa

revision = "0002_required_media_password"
down_revision = "0001_remains"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("researchers", sa.Column("password", sa.String(255), nullable=True))
    op.execute("UPDATE researchers SET password = '!' WHERE password IS NULL")
    op.alter_column("researchers", "password", existing_type=sa.String(255), nullable=False)
    op.execute("UPDATE remains SET image_url = '/static/remains/wood.jpg' WHERE image_url IS NULL")
    op.execute("UPDATE remains SET video_url = '/static/remains/wood-video.mp4' WHERE video_url IS NULL")
    op.alter_column("remains", "image_url", existing_type=sa.String(1024), nullable=False)
    op.alter_column("remains", "video_url", existing_type=sa.String(1024), nullable=False)


def downgrade():
    op.alter_column("remains", "video_url", existing_type=sa.String(1024), nullable=True)
    op.alter_column("remains", "image_url", existing_type=sa.String(1024), nullable=True)
    op.drop_column("researchers", "password")
