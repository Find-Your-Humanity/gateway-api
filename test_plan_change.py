#!/usr/bin/env python3
"""
요금제 변경 기능 테스트 스크립트
"""

import requests
import json
from datetime import datetime

# 테스트 설정
BASE_URL = "http://localhost:8000"  # 또는 실제 서버 URL
TEST_USER_EMAIL = "test@example.com"  # 테스트할 사용자 이메일
TEST_USER_PASSWORD = "test123"  # 테스트 사용자 비밀번호

def test_plan_change():
    """요금제 변경 테스트"""
    
    print("🚀 요금제 변경 기능 테스트 시작")
    print("=" * 50)
    
    # 1. 로그인하여 토큰 획득
    print("1️⃣ 사용자 로그인...")
    login_data = {
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    }
    
    try:
        login_response = requests.post(f"{BASE_URL}/api/auth/login", json=login_data)
        if login_response.status_code != 200:
            print(f"❌ 로그인 실패: {login_response.status_code}")
            print(f"응답: {login_response.text}")
            return
        
        login_result = login_response.json()
        if not login_result.get("success"):
            print(f"❌ 로그인 실패: {login_result.get('message', '알 수 없는 오류')}")
            return
        
        token = login_result.get("data", {}).get("access_token")
        if not token:
            print("❌ 액세스 토큰을 찾을 수 없습니다.")
            return
        
        print("✅ 로그인 성공")
        print(f"토큰: {token[:20]}...")
        
    except Exception as e:
        print(f"❌ 로그인 중 오류 발생: {e}")
        return
    
    # 2. 현재 요금제 정보 조회
    print("\n2️⃣ 현재 요금제 정보 조회...")
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        current_plan_response = requests.get(f"{BASE_URL}/api/billing/current-plan", headers=headers)
        if current_plan_response.status_code == 200:
            current_plan = current_plan_response.json()
            print(f"✅ 현재 요금제: {current_plan.get('data', {}).get('plan', {}).get('name', '알 수 없음')}")
        else:
            print(f"⚠️ 현재 요금제 조회 실패: {current_plan_response.status_code}")
    except Exception as e:
        print(f"⚠️ 현재 요금제 조회 중 오류: {e}")
    
    # 3. 사용 가능한 요금제 목록 조회
    print("\n3️⃣ 사용 가능한 요금제 목록 조회...")
    
    try:
        plans_response = requests.get(f"{BASE_URL}/api/billing/plans", headers=headers)
        if plans_response.status_code == 200:
            plans = plans_response.json()
            print("✅ 사용 가능한 요금제:")
            for plan in plans.get("data", []):
                print(f"  - ID: {plan['id']}, 이름: {plan['name']}, 가격: {plan['price']}원")
        else:
            print(f"⚠️ 요금제 목록 조회 실패: {plans_response.status_code}")
    except Exception as e:
        print(f"⚠️ 요금제 목록 조회 중 오류: {e}")
    
    # 4. Analytics 데이터 조회 (변경 전)
    print("\n4️⃣ 변경 전 Analytics 데이터 조회...")
    
    try:
        analytics_response = requests.get(f"{BASE_URL}/api/dashboard/usage-limits", headers=headers)
        if analytics_response.status_code == 200:
            analytics = analytics_response.json()
            print(f"✅ 현재 플랜: {analytics.get('data', {}).get('plan', '알 수 없음')}")
            print(f"✅ 플랜 표시명: {analytics.get('data', {}).get('planDisplayName', '알 수 없음')}")
            limits = analytics.get('data', {}).get('limits', {})
            print(f"✅ 제한량: 분당 {limits.get('perMinute', 0)}, 일일 {limits.get('perDay', 0)}, 월간 {limits.get('perMonth', 0)}")
        else:
            print(f"⚠️ Analytics 데이터 조회 실패: {analytics_response.status_code}")
    except Exception as e:
        print(f"⚠️ Analytics 데이터 조회 중 오류: {e}")
    
    # 5. 요금제 변경 테스트 (starter로 변경)
    print("\n5️⃣ 요금제 변경 테스트 (starter로 변경)...")
    
    try:
        change_data = {"plan_id": 2}  # starter 플랜 ID (실제 환경에 맞게 조정 필요)
        change_response = requests.post(f"{BASE_URL}/api/billing/change-plan", 
                                     json=change_data, headers=headers)
        
        if change_response.status_code == 200:
            change_result = change_response.json()
            if change_result.get("success"):
                print("✅ 요금제 변경 성공!")
                print(f"메시지: {change_result.get('message', '')}")
                print(f"적용일: {change_result.get('effective_date', '')}")
            else:
                print(f"❌ 요금제 변경 실패: {change_result.get('message', '알 수 없는 오류')}")
        else:
            print(f"❌ 요금제 변경 요청 실패: {change_response.status_code}")
            print(f"응답: {change_response.text}")
    except Exception as e:
        print(f"❌ 요금제 변경 중 오류 발생: {e}")
    
    # 6. 변경 후 Analytics 데이터 조회
    print("\n6️⃣ 변경 후 Analytics 데이터 조회...")
    
    try:
        analytics_response_after = requests.get(f"{BASE_URL}/api/dashboard/usage-limits", headers=headers)
        if analytics_response_after.status_code == 200:
            analytics_after = analytics_response_after.json()
            print(f"✅ 변경 후 플랜: {analytics_after.get('data', {}).get('plan', '알 수 없음')}")
            print(f"✅ 변경 후 플랜 표시명: {analytics_after.get('data', {}).get('planDisplayName', '알 수 없음')}")
            limits_after = analytics_after.get('data', {}).get('limits', {})
            print(f"✅ 변경 후 제한량: 분당 {limits_after.get('perMinute', 0)}, 일일 {limits_after.get('perDay', 0)}, 월간 {limits_after.get('perMonth', 0)}")
        else:
            print(f"⚠️ 변경 후 Analytics 데이터 조회 실패: {analytics_response_after.status_code}")
    except Exception as e:
        print(f"⚠️ 변경 후 Analytics 데이터 조회 중 오류: {e}")
    
    print("\n" + "=" * 50)
    print("🏁 테스트 완료")

if __name__ == "__main__":
    test_plan_change()
