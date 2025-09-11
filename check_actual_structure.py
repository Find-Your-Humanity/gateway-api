#!/usr/bin/env python3
"""
실제 데이터베이스 구조 확인 스크립트
"""

from src.config.database import get_db_connection

def check_actual_structure():
    print("=== 실제 데이터베이스 구조 확인 ===")
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                print("=== request_logs 테이블 구조 ===")
                cursor.execute("SHOW COLUMNS FROM request_logs")
                for row in cursor.fetchall():
                    print(f"  {row['Field']}: {row['Type']}")
                
                print("\n=== api_request_logs 테이블 구조 ===")
                cursor.execute("SHOW COLUMNS FROM api_request_logs")
                for row in cursor.fetchall():
                    print(f"  {row['Field']}: {row['Type']}")
                
                print("\n=== api_request_logs 테이블 샘플 데이터 ===")
                cursor.execute("SELECT * FROM api_request_logs LIMIT 1")
                sample = cursor.fetchone()
                if sample:
                    print("샘플 데이터:")
                    for key, value in sample.items():
                        print(f"  {key}: {value}")
                else:
                    print("데이터가 없습니다.")
                    
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_actual_structure()
