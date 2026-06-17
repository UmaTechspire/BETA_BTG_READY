import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Print all database configuration
print("=" * 50)
print("DATABASE CONFIGURATION TEST")
print("=" * 50)
print(f"DB_USER: {os.getenv('DB_USER')}")
print(f"DB_PASSWORD: {os.getenv('DB_PASSWORD')}")
print(f"DB_HOST: {os.getenv('DB_HOST')}")
print(f"DB_PORT: {os.getenv('DB_PORT')}")
print(f"DB_NAME_USER: {os.getenv('DB_NAME_USER')}")
print(f"DB_NAME_FINANCE: {os.getenv('DB_NAME_FINANCE')}")
print(f"DB_NAME_PURCHASE: {os.getenv('DB_NAME_PURCHASE')}")
print(f"DB_NAME_MASTER: {os.getenv('DB_NAME_MASTER')}")
print("=" * 50)

# Test database connection
import mysql.connector

try:
    conn = mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME_FINANCE'),
        ssl_disabled=True
    )
    cursor = conn.cursor()
    cursor.execute("SELECT DATABASE(), USER()")
    result = cursor.fetchone()
    print(f"\n✅ Successfully connected to database!")
    print(f"   Current Database: {result[0]}")
    print(f"   Current User: {result[1]}")
    cursor.close()
    conn.close()
except Exception as e:
    print(f"\n❌ Connection failed: {e}")
