from alembic import op
import sqlalchemy as sa

revision='0007_compensation_archive';down_revision='0006_calendar';branch_labels=None;depends_on=None
def upgrade():
 op.add_column('employees',sa.Column('archived_at',sa.DateTime(),nullable=True))
 op.create_table('compensation_configurations',sa.Column('id',sa.Uuid(),primary_key=True),sa.Column('employee_id',sa.Uuid(),sa.ForeignKey('employees.id'),nullable=False),sa.Column('monthly_salary',sa.Numeric(12,2),nullable=False),sa.Column('overtime_hourly_rate',sa.Numeric(12,2),nullable=False),sa.Column('late_deduction_amount',sa.Numeric(12,2),nullable=False),sa.Column('effective_from',sa.Date(),nullable=False),sa.Column('effective_to',sa.Date()),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('created_by',sa.Uuid(),sa.ForeignKey('employees.id'),nullable=False),sa.CheckConstraint('effective_to IS NULL OR effective_to >= effective_from',name='ck_compensation_dates'))
 op.create_index('ix_compensation_configurations_employee_id','compensation_configurations',['employee_id'])
 op.create_index('ix_compensation_configurations_effective_from','compensation_configurations',['effective_from'])
def downgrade():
 op.drop_table('compensation_configurations');op.drop_column('employees','archived_at')
