"""leave management foundation"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_leave_management"
down_revision = "0001_employee_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    leave_type = postgresql.ENUM(
        "CASUAL", "MEDICAL", "EMERGENCY", "DAY_OFF", name="leave_type", create_type=False
    )
    leave_status = postgresql.ENUM(
        "PENDING", "APPROVED", "REJECTED", name="leave_status", create_type=False
    )
    leave_duration = postgresql.ENUM(
        "FULL_DAY", "HALF_DAY", name="leave_duration", create_type=False
    )
    half_day_period = postgresql.ENUM(
        "MORNING", "AFTERNOON", name="half_day_period", create_type=False
    )
    decision_source = postgresql.ENUM(
        "AUTOMATIC_POLICY", "MANAGER", name="leave_decision_source", create_type=False
    )
    for enum in (leave_type, leave_status, leave_duration, half_day_period, decision_source):
        enum.create(bind, checkfirst=True)
    op.create_table(
        "leave_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("leave_type", leave_type, nullable=False),
        sa.Column("status", leave_status, nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("duration", leave_duration, nullable=False),
        sa.Column("half_day_period", half_day_period),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("decided_by_id", sa.Uuid(), sa.ForeignKey("employees.id")),
        sa.Column("decided_at", sa.DateTime()),
        sa.Column("decision_note", sa.String(1000)),
        sa.Column("decision_source", decision_source),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_leave_requests_employee_id", "leave_requests", ["employee_id"])


def downgrade() -> None:
    op.drop_index("ix_leave_requests_employee_id", table_name="leave_requests")
    op.drop_table("leave_requests")
    for name in (
        "leave_decision_source",
        "half_day_period",
        "leave_duration",
        "leave_status",
        "leave_type",
    ):
        op.execute(f"DROP TYPE IF EXISTS {name}")
