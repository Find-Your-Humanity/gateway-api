#!/usr/bin/env python3
"""
수정된 통합 로그 쿼리 테스트 스크립트
"""

from src.utils.log_queries import get_api_status_query, get_time_filter
from src.config.database import get_db_connection

def test_fixed_queries():
    print("=== 수정된 통합 로그 쿼리 테스트 ===")
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 수정된 쿼리 실행
                query = get_api_status_query(get_time_filter(1))
                print("실행할 쿼리:")
                print(query[:200] + "...")
                
                cursor.execute(query)
                results = cursor.fetchall()
                print(f"\n결과 개수: {len(results)}")
                
                for result in results[:3]:
                    print(f"  - {result['endpoint']}: {result['total_requests']} requests")
                
                print("\n=== 테이블별 개별 조회 테스트 ===")
                # request_logs 테이블 조회
                cursor.execute("SELECT COUNT(*) as count FROM request_logs WHERE request_time >= NOW() - INTERVAL 1 HOUR")
                request_logs_count = cursor.fetchone()['count']
                print(f"request_logs 테이블 (최근 1시간): {request_logs_count} 개")
                
                # api_request_logs 테이블 조회
                cursor.execute("SELECT COUNT(*) as count FROM api_request_logs WHERE created_at >= NOW() - INTERVAL 1 HOUR")
                api_request_logs_count = cursor.fetchone()['count']
                print(f"api_request_logs 테이블 (최근 1시간): {api_request_logs_count} 개")
                
                print(f"\n총 통합 로그 수: {request_logs_count + api_request_logs_count} 개")
                
                print("\n✅ 통합 로그 쿼리가 성공적으로 작동합니다!")
                
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_fixed_queries()
