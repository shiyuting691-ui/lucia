"""
数据库连接和初始化
本地：SQLite（marketing.db）
生产：修改 DATABASE_URL 为 postgresql://... 即可
"""
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

from .models import Base, Product, School

# ── 数据库 URL ──
_BASE_DIR = Path(__file__).parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_BASE_DIR}/marketing.db")

# SQLite 需要设置 check_same_thread=False
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, echo=False)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db(config: dict = None):
    """创建所有表，并从 config.yaml 初始化基础数据"""
    Base.metadata.create_all(bind=engine)
    if config:
        _seed_from_config(config)
    print(f"✅ 数据库已初始化：{DATABASE_URL}")


def _seed_from_config(config: dict):
    """把 config.yaml 里的 products / schools 同步到数据库（幂等）"""
    with get_session() as session:
        # 同步产品
        for p in config.get("products", []):
            existing = session.get(Product, p["id"])
            if not existing:
                session.add(Product(
                    id=p["id"],
                    name=p["name"],
                    description=p.get("description", ""),
                    price_range=p.get("price_range", ""),
                    target=p.get("target", ""),
                    selling_points=p.get("selling_points", []),
                ))

        # 同步学校
        for country, schools in config.get("schools", {}).items():
            country_label = "UK" if country == "uk" else "Australia"
            for s in schools:
                from sqlalchemy import select
                exists = session.execute(
                    select(School).where(School.name == s["name"])
                ).scalar_one_or_none()
                if not exists:
                    session.add(School(
                        name=s["name"],
                        full_name=s.get("full_name", ""),
                        country=country_label,
                        popular_majors=s.get("popular_majors", []),
                        exam_period=s.get("exam_period", []),
                    ))

        session.commit()


@contextmanager
def get_session() -> Session:
    """上下文管理器，自动提交/回滚"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db():
    """FastAPI 依赖注入用"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
