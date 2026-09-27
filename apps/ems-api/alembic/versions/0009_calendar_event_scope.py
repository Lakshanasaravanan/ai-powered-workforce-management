from alembic import op
import sqlalchemy as sa

revision = '0009_calendar_event_scope'
down_revision = '0008_company_holidays'
branch_labels = None
depends_on = None

def upgrade():
    scope = sa.Enum('PRIVATE', 'COMPANY', name='eventscope')
    scope.create(op.get_bind(), checkfirst=True)
    op.add_column('calendar_events', sa.Column('scope', scope, nullable=True))
    op.execute("UPDATE calendar_events SET scope = 'COMPANY' WHERE scope IS NULL")
    op.alter_column('calendar_events', 'scope', nullable=False)

def downgrade():
    op.drop_column('calendar_events', 'scope')
    sa.Enum(name='eventscope').drop(op.get_bind(), checkfirst=True)
