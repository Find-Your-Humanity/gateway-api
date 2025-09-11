#!/usr/bin/env python3
"""
최종 통합 로그 쿼리 테스트 스크립트
"""

from src.utils.log_queries import get_api_status_query, get_time_filter
from src.config.database import get_db_connection

def final_test():
    print("=== 최종 통합 로그 쿼리 테스트 ===")
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 수정된 통합 쿼리 실행
                query = get_api_status_query(get_time_filter(1))
                print("실행할 쿼리:")
                print(query[:300] + "...")
                
                cursor.execute(query)
                results = cursor.fetchall()
                print(f"\n✅ 성공! 결과 개수: {len(results)}")
                
                for result in results[:3]:
                    print(f"  - {result['endpoint']}: {result['total_requests']} requests")
                
                print("\n=== 실시간 모니터링 API 테스트 ===")
                # 실시간 모니터링 API의 다른 쿼리들도 테스트
                from src.utils.log_queries import get_response_time_query, get_error_rate_query, get_tps_query, get_system_summary_query
                
                # 응답 시간 쿼리
                cursor.execute(get_response_time_query(get_time_filter(1), "5분", 5))
                response_results = cursor.fetchall()
                print(f"응답 시간 데이터: {len(response_results)} 개")
                
                # 에러율 쿼리
                cursor.execute(get_error_rate_query(get_time_filter(1), "5분", 5))
                error_results = cursor.fetchall()
                print(f"에러율 데이터: {len(error_results)} 개")
                
                # TPS 쿼리
                cursor.execute(get_tps_query(get_time_filter(1), 10))
                tps_results = cursor.fetchall()
                print(f"TPS 데이터: {len(tps_results)} 개")
                
                # 시스템 요약 쿼리
                cursor.execute(get_system_summary_query(get_time_filter(1)))
                summary = cursor.fetchone()
                print(f"시스템 요약: {summary['total_requests_1h']} requests")
                
                print("\n🎉 모든 통합 로그 쿼리가 성공적으로 작동합니다!")
                
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    final_test()
