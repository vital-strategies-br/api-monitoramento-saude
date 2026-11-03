import os

# Settings require DATABASE_URL at import time; tests never connect to it.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
