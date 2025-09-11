#!/usr/bin/env python3
"""
테이블 구조 확인 스크립트
"""

from src.config.database import get_db_connection

def check_table_structure():
    print("=== 테이블 구조 확인 ===")
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                print("=== request_logs 테이블 구조 ===")
                cursor.execute("DESCRIBE request_logs")
                for row in cursor.fetchall():
                    print(f"  {row['Field']}: {row['Type']}")
                
                print("\n=== api_request_logs 테이블 구조 ===")
                cursor.execute("DESCRIBE api_request_logs")
                for row in cursor.fetchall():
                    print(f"  {row['Field']}: {row['Type']}")
                    
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_table_structure()
