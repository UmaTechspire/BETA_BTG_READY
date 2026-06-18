import os
import urllib.parse  # <--- Import this library
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv

load_dotenv()

# 1. URL Encode the credentials to handle special chars like '@'
db_user = urllib.parse.quote_plus(os.getenv('DB_USER'))
db_password = urllib.parse.quote_plus(os.getenv('DB_PASSWORD'))
db_host = os.getenv('DB_HOST')
db_port = os.getenv('DB_PORT')
# Database Names
DB_NAME_FINANCE = os.getenv('DB_NAME_FINANCE', 'btggasify_finance_live')
DB_NAME_USER = os.getenv('DB_NAME_USER', 'btggasify_live')
DB_NAME_USER_NEW = os.getenv('DB_NAME_USER_NEW', 'btggasify_userpanel_live')
DB_NAME_PURCHASE = os.getenv('DB_NAME_PURCHASE', 'btggasify_purchase_live')
DB_NAME_MASTER = os.getenv('DB_NAME_MASTER', 'btggasify_masterpanel_live')
DB_NAME_OLD = os.getenv('DB_NAME_OLD', 'btggasify_live')

# Default DB for main connection
db_name = DB_NAME_FINANCE

# 2. Build the Safe Connection String
DATABASE_URL = (
    f"mysql+aiomysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
)

engine = create_async_engine(DATABASE_URL, echo=True, pool_pre_ping=True, pool_recycle=280)
SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

# Dependency to get DB session
async def get_db():
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()