from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from src.config.settings import DATABASE_URL

# 配料依赖「先取单行锁，再读最新库存」。MySQL 默认 REPEATABLE READ 的普通读会
# 命中事务快照，看不到并发事务刚提交的库存；改用 READ COMMITTED 让加锁后的读取
# 始终基于最新已提交数据。SQLite 不支持该设置，跳过。
_MYSQL = DATABASE_URL.startswith('mysql')
engine = create_engine(DATABASE_URL, pool_pre_ping=True,
                       isolation_level='READ COMMITTED' if _MYSQL else None)
Session = sessionmaker(engine, expire_on_commit=False)
class Base(DeclarativeBase): pass
def get_db():
    with Session() as s: yield s
