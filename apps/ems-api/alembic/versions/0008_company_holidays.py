from alembic import op
import sqlalchemy as sa


revision = "0008_company_holidays"
down_revision = "0007_compensation_archive"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "company_holidays",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("holiday_date", sa.Date(), nullable=False, unique=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_company_holidays_holiday_date", "company_holidays", ["holiday_date"])


def downgrade():
    op.drop_table("company_holidays")
