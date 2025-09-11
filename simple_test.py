#!/usr/bin/env python3
"""
간단한 통합 로그 쿼리 테스트 스크립트
"""

from src.utils.log_queries import get_api_status_query, get_time_filter
from src.config.database import get_db_connection

def simple_test():
    print("=== 간단한 통합 로그 쿼리 테스트 ===")
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # request_logs 테이블 조회
                print("1. request_logs 테이블 조회:")
                cursor.execute(get_api_status_query(get_time_filter(1)))
                request_logs_data = cursor.fetchall()
                print(f"   결과: {len(request_logs_data)} 개")
                for row in request_logs_data[:2]:
                    print(f"   - {row['endpoint']}: {row['total_requests']} requests")
                
                # api_request_logs 테이블 직접 조회
                print("\n2. api_request_logs 테이블 직접 조회:")
                cursor.execute("""
                    SELECT 
                        path as endpoint,
                        COUNT(*) as total_requests,
                        COALESCE(SUM(CASE WHEN status_code BETWEEN 200 AND 399 THEN 1 ELSE 0 END), 0) as success_count,
                        COALESCE(SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END), 0) as error_count,
                        COALESCE(AVG(response_time), 0) as avg_response_time,
                        MAX(created_at) as last_request_time
                    FROM api_request_logs 
                    WHERE created_at >= NOW() - INTERVAL 1 HOUR
                    GROUP BY path
                    ORDER BY total_requests DESC
                """)
                api_request_logs_data = cursor.fetchall()
                print(f"   결과: {len(api_request_logs_data)} 개")
                for row in api_request_logs_data[:2]:
                    print(f"   - {row['endpoint']}: {row['total_requests']} requests")
                
                print("\n✅ 두 테이블 모두 정상적으로 조회됩니다!")
                print("🎉 실시간 모니터링 대시보드에서 통합 로그 데이터를 표시할 수 있습니다!")
                
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    simple_test()
