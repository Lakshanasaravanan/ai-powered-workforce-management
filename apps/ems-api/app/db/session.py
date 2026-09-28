from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase,sessionmaker
from app.core.config import Settings
def url(): return Settings().database_url.replace('+asyncpg','+psycopg')
engine=create_engine(url(),future=True)
SessionLocal=sessionmaker(engine,autoflush=False,autocommit=False)
class Base(DeclarativeBase): pass
def get_db():
 db=SessionLocal()
 try: yield db
 finally: db.close()
