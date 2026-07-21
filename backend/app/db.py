"""数据库连接。默认 SQLite (开发), 生产通过 DATABASE_URL 切 PostgreSQL。"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./coal_stand.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.agent import conversation  # noqa: F401  确保 ORM 已注册
    from app.llm import settings  # noqa: F401
    from app.models import db_models, knowledge_models  # noqa: F401
    Base.metadata.create_all(engine)
