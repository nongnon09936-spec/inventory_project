import os
import mysql.connector
from mysql.connector import pooling

try:
    # สร้าง Pool เผื่อไว้ดึงใช้งาน ป้องกัน Error Too Many Connections
    db_pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="psru_pool",
        pool_size=5,
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "your_db_name"),
        port=int(os.environ.get("DB_PORT", 3306)),
        autocommit=False # ปิด Auto Commit เพื่อใช้ Transaction
    )
except Exception as e:
    print(f"Error creating pool: {e}")
    db_pool = None

def get_db_connection():
    if db_pool:
        return db_pool.get_connection()
    # สำรองกรณี Pool ไม่ทำงาน
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", "rootroot"),
        database=os.environ.get("DB_NAME", "office_inventory"),
        port=int(os.environ.get("DB_PORT", 3306)),
        autocommit=False
    )