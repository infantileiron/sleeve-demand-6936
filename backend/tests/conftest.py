import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DB_PATH = pathlib.Path('/tmp/sleeve_test.db')
os.environ.setdefault('DATABASE_URL', f'sqlite+pysqlite:///{DB_PATH}')
os.environ.setdefault('REDIS_URL', 'redis://127.0.0.1:6399/0')
os.environ.setdefault('JWT_SECRET', 'test-secret-key-test-secret-key-1234')
os.environ.setdefault('SEED_DEMO', 'false')
