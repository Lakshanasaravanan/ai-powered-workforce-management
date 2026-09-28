from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010_attendance_foundation"
down_revision = "0009_calendar_event_scope"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    status = postgresql.ENUM("PRESENT", "LEAVE", "ABSENT", name="attendancestatus", create_type=False)
    source = postgresql.ENUM("FACE", "APPROVED_LEAVE", "ADMIN_OVERRIDE", name="attendancesource", create_type=False)
    postgresql.ENUM("PRESENT", "LEAVE", "ABSENT", name="attendancestatus").create(bind, checkfirst=True)
    postgresql.ENUM("FACE", "APPROVED_LEAVE", "ADMIN_OVERRIDE", name="attendancesource").create(bind, checkfirst=True)
    op.create_table(
        "attendance_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("regular_check_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("regular_check_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("leave_request_id", sa.Uuid(), nullable=True),
        sa.Column("leave_type", sa.String(length=32), nullable=True),
        sa.Column("source", source, nullable=False),
        sa.Column("admin_modified_by", sa.Uuid(), nullable=True),
        sa.Column("admin_modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_modification_reason", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["admin_modified_by"], ["employees.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["leave_request_id"], ["leave_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "attendance_date", name="uq_attendance_employee_date"),
    )
    op.create_index("ix_attendance_employee_date", "attendance_records", ["employee_id", "attendance_date"], unique=False)


def downgrade():
    op.drop_index("ix_attendance_employee_date", table_name="attendance_records")
    op.drop_table("attendance_records")
    bind = op.get_bind()
    sa.Enum(name="attendancesource").drop(bind, checkfirst=True)
    sa.Enum(name="attendancestatus").drop(bind, checkfirst=True)
