#!/usr/bin/env python3
"""
캡차 API 사용량 추적 테스트 스크립트
"""

import requests
import json
import time
from datetime import datetime

# 테스트 설정
BASE_URL = "http://localhost:8000"  # 또는 실제 서버 URL
API_KEY = "your_test_api_key_here"  # 테스트용 API 키

def test_captcha_usage():
    """캡차 API 사용량 테스트"""
    
    print("🚀 캡차 API 사용량 추적 테스트 시작")
    print("=" * 50)
    
    # 1. next-captcha API 호출 (사용량 증가)
    print("1️⃣ next-captcha API 호출...")
    
    headers = {
        "X-API-Key": API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "behavior_data": {
            "mouseMovements": [{"x": 100, "y": 200}, {"x": 150, "y": 250}],
            "mouseClicks": [{"x": 100, "y": 200}],
            "keyboardEvents": ["keydown", "keyup"]
        },
        "site_key": "test_site_key"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/next-captcha", 
                               json=payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ next-captcha API 호출 성공")
            print(f"응답: {result.get('next_captcha', 'N/A')}")
        else:
            print(f"❌ next-captcha API 호출 실패: {response.status_code}")
            print(f"응답: {response.text}")
            return
            
    except Exception as e:
        print(f"❌ next-captcha API 호출 중 오류: {e}")
        return
    
    # 2. 잠시 대기
    print("\n2️⃣ 2초 대기...")
    time.sleep(2)
    
    # 3. verify-handwriting API 호출 (사용량 증가)
    print("3️⃣ verify-handwriting API 호출...")
    
    handwriting_payload = {
        "image_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    }
    
    try:
        response = requests.post(f"{BASE_URL}/api/verify-handwriting", 
                               json=handwriting_payload, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            print("✅ verify-handwriting API 호출 성공")
            print(f"검증 결과: {result.get('success', 'N/A')}")
        else:
            print(f"❌ verify-handwriting API 호출 실패: {response.status_code}")
            print(f"응답: {response.text}")
            
    except Exception as e:
        print(f"❌ verify-handwriting API 호출 중 오류: {e}")
    
    # 4. 사용량 확인 (데이터베이스 직접 조회)
    print("\n4️⃣ 사용량 확인...")
    print("💡 데이터베이스에서 user_usage_tracking 테이블을 직접 확인하세요:")
    print("""
    SELECT 
        user_id,
        tracking_date,
        per_minute_count,
        per_day_count,
        per_month_count,
        last_updated
    FROM user_usage_tracking 
    WHERE tracking_date = CURDATE()
    ORDER BY last_updated DESC;
    """)
    
    print("\n" + "=" * 50)
    print("🏁 테스트 완료")
    print("\n📊 예상 결과:")
    print("- per_minute_count: 2 (API 2번 호출)")
    print("- per_day_count: 2 (오늘 총 2번 호출)")
    print("- per_month_count: 2 (이번 달 총 2번 호출)")

if __name__ == "__main__":
    test_captcha_usage()
