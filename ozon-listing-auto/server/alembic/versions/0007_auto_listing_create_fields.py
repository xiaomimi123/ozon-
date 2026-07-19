"""auto listing create fields: listing_drafts type_id/尺寸/重量/单位"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"


def upgrade():
    op.add_column("listing_drafts", sa.Column("type_id", sa.Integer(), nullable=True))
    op.add_column("listing_drafts", sa.Column("depth", sa.Integer(), nullable=True))
    op.add_column("listing_drafts", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("listing_drafts", sa.Column("height", sa.Integer(), nullable=True))
    op.add_column("listing_drafts", sa.Column("weight", sa.Integer(), nullable=True))
    op.add_column("listing_drafts", sa.Column("dimension_unit", sa.String(length=8), server_default="mm", nullable=False))
    op.add_column("listing_drafts", sa.Column("weight_unit", sa.String(length=8), server_default="g", nullable=False))


def downgrade():
    for c in ("type_id", "depth", "width", "height", "weight", "dimension_unit", "weight_unit"):
        op.drop_column("listing_drafts", c)
