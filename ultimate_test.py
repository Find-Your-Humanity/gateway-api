#!/usr/bin/env python3
"""
최종 통합 로그 쿼리 테스트 스크립트
"""

from src.utils.log_queries import get_api_status_query, get_api_status_query_api_logs, get_time_filter
from src.config.database import get_db_connection

def ultimate_test():
    print("=== 최종 통합 로그 쿼리 테스트 ===")
    
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 1. request_logs 테이블 조회
                print("1. request_logs 테이블 조회:")
                cursor.execute(get_api_status_query(get_time_filter(1)))
                request_logs_data = cursor.fetchall()
                print(f"   결과: {len(request_logs_data)} 개")
                for row in request_logs_data[:2]:
                    print(f"   - {row['endpoint']}: {row['total_requests']} requests")
                
                # 2. api_request_logs 테이블 조회
                print("\n2. api_request_logs 테이블 조회:")
                cursor.execute(get_api_status_query_api_logs(get_time_filter(1)))
                api_request_logs_data = cursor.fetchall()
                print(f"   결과: {len(api_request_logs_data)} 개")
                for row in api_request_logs_data[:2]:
                    print(f"   - {row['endpoint']}: {row['total_requests']} requests")
                
                # 3. 두 결과 합치기 (실시간 모니터링 API와 동일한 로직)
                print("\n3. 두 결과 합치기:")
                combined_data = {}
                
                # request_logs 데이터 추가
                for row in request_logs_data:
                    endpoint = row["endpoint"]
                    combined_data[endpoint] = {
                        "endpoint": endpoint,
                        "total_requests": row["total_requests"],
                        "success_count": row["success_count"],
                        "error_count": row["error_count"],
                        "avg_response_time": row["avg_response_time"],
                        "last_request_time": row["last_request_time"]
                    }
                
                # api_request_logs 데이터 추가/합치기
                for row in api_request_logs_data:
                    endpoint = row["endpoint"]
                    if endpoint in combined_data:
                        # 기존 데이터와 합치기
                        combined_data[endpoint]["total_requests"] += row["total_requests"]
                        combined_data[endpoint]["success_count"] += row["success_count"]
                        combined_data[endpoint]["error_count"] += row["error_count"]
                        combined_data[endpoint]["avg_response_time"] = (combined_data[endpoint]["avg_response_time"] + row["avg_response_time"]) / 2
                        if row["last_request_time"] > combined_data[endpoint]["last_request_time"]:
                            combined_data[endpoint]["last_request_time"] = row["last_request_time"]
                    else:
                        # 새로운 엔드포인트 추가
                        combined_data[endpoint] = {
                            "endpoint": endpoint,
                            "total_requests": row["total_requests"],
                            "success_count": row["success_count"],
                            "error_count": row["error_count"],
                            "avg_response_time": row["avg_response_time"],
                            "last_request_time": row["last_request_time"]
                        }
                
                print(f"   통합 결과: {len(combined_data)} 개 엔드포인트")
                for endpoint, data in list(combined_data.items())[:3]:
                    success_rate = (data["success_count"] / data["total_requests"] * 100) if data["total_requests"] > 0 else 0
                    print(f"   - {endpoint}: {data['total_requests']} requests (성공률: {success_rate:.1f}%)")
                
                print("\n🎉 통합 로그 쿼리가 성공적으로 작동합니다!")
                print("✅ 실시간 모니터링 대시보드에서 두 로그 테이블의 데이터를 완전히 통합하여 표시할 수 있습니다!")
                
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    ultimate_test()
