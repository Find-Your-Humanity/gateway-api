#!/usr/bin/env python3
"""
단계별 쿼리 테스트 스크립트
"""

from src.config.database import get_db_connection

def test_step_by_step():
    print("=== 단계별 쿼리 테스트 ===")
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 1. request_logs 테이블만 조회
                print("1. request_logs 테이블 조회:")
                cursor.execute("SELECT COUNT(*) as count FROM request_logs WHERE request_time >= NOW() - INTERVAL 1 HOUR")
                result1 = cursor.fetchone()
                print(f"   결과: {result1['count']} 개")
                
                # 2. api_request_logs 테이블만 조회
                print("2. api_request_logs 테이블 조회:")
                cursor.execute("SELECT COUNT(*) as count FROM api_request_logs WHERE created_at >= NOW() - INTERVAL 1 HOUR")
                result2 = cursor.fetchone()
                print(f"   결과: {result2['count']} 개")
                
                # 3. UNION ALL 쿼리 테스트
                print("3. UNION ALL 쿼리 테스트:")
                cursor.execute("""
                    SELECT COUNT(*) as total FROM (
                        SELECT request_time FROM request_logs WHERE request_time >= NOW() - INTERVAL 1 HOUR
                        UNION ALL
                        SELECT created_at as request_time FROM api_request_logs WHERE created_at >= NOW() - INTERVAL 1 HOUR
                    ) as combined_logs
                """)
                result3 = cursor.fetchone()
                print(f"   결과: {result3['total']} 개")
                
                # 4. 전체 통합 쿼리 테스트
                print("4. 전체 통합 쿼리 테스트:")
                cursor.execute("""
                    SELECT 
                        path as endpoint,
                        COUNT(*) as total_requests
                    FROM (
                        SELECT path, request_time FROM request_logs WHERE request_time >= NOW() - INTERVAL 1 HOUR
                        UNION ALL
                        SELECT path, created_at as request_time FROM api_request_logs WHERE created_at >= NOW() - INTERVAL 1 HOUR
                    ) as combined_logs
                    GROUP BY path
                    ORDER BY total_requests DESC
                    LIMIT 5
                """)
                results = cursor.fetchall()
                print(f"   결과 개수: {len(results)}")
                for result in results:
                    print(f"   - {result['endpoint']}: {result['total_requests']} requests")
                
                print("\n✅ 모든 쿼리가 성공적으로 작동합니다!")
                
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_step_by_step()
