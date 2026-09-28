"""notification inbox foundation"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0003_notifications"
down_revision = "0002_leave_management"
branch_labels = None
depends_on = None


def upgrade() -> None:
    category = postgresql.ENUM(
        "LEAVE", "CHAT", "CALENDAR", "SYSTEM", name="notification_category", create_type=False
    )
    category.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("recipient_id", sa.Uuid(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("category", category, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("read_at", sa.DateTime()),
        sa.Column("related_entity_type", sa.String(50)),
        sa.Column("related_entity_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_notifications_recipient_id", "notifications", ["recipient_id"])


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_id", table_name="notifications")
    op.drop_table("notifications")
    op.execute("DROP TYPE IF EXISTS notification_category")
