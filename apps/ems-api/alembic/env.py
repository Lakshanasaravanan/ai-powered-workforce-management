from alembic import context
from app.db.session import Base
from app.models.employee import Employee
from app.models.leave import LeaveRequest
from app.models.notification import Notification
from app.core.config import Settings
config=context.config
config.set_main_option('sqlalchemy.url', Settings().database_url.replace('+asyncpg', '+psycopg'))
target_metadata=Base.metadata
def run_migrations_offline(): context.configure(url=config.get_main_option('sqlalchemy.url'),target_metadata=target_metadata,literal_binds=True); context.run_migrations()
def run_migrations_online():
 from sqlalchemy import engine_from_config,pool
 with engine_from_config(config.get_section(config.config_ini_section),prefix='sqlalchemy.',poolclass=pool.NullPool).begin() as c: context.configure(connection=c,target_metadata=target_metadata); context.run_migrations()
if context.is_offline_mode():run_migrations_offline()
else:run_migrations_online()
