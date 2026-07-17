"""m5 publish pacing"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"

def upgrade():
    op.create_table("publish_pace",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("task_id", sa.Integer, sa.ForeignKey("collect_tasks.id"), index=True),
        sa.Column("min_interval_sec", sa.Integer, server_default="60", nullable=False),
        sa.Column("max_interval_sec", sa.Integer, server_default="180", nullable=False),
        sa.Column("daily_limit", sa.Integer, server_default="200", nullable=False),
        sa.Column("active_hours", postgresql.JSONB, server_default="[9, 23]", nullable=False),
        sa.Column("wait_ozon_approval", sa.Boolean, server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

def downgrade():
    op.drop_table("publish_pace")
