from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any
import os
import json
import secrets
import hashlib
from datetime import datetime, timedelta
from src.config.database import get_db_connection
from src.routes.auth import get_current_user_from_request
from src.services.usage_service import usage_service

router = APIRouter(prefix="/api", tags=["captcha"])

def verify_api_key_with_secret(api_key: str, secret_key: str) -> Dict[str, Any]:
    """
    API Key와 Secret Key를 함께 검증합니다.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # API Key와 Secret Key 조회
                cursor.execute("""
                    SELECT ak.id, ak.user_id, ak.name, ak.is_active, ak.rate_limit_per_minute, 
                           ak.rate_limit_per_day, ak.usage_count, ak.last_used_at,
                           u.email, us.plan_id, p.name as plan_name, p.max_requests_per_month
                    FROM api_keys ak
                    JOIN users u ON ak.user_id = u.id
                    LEFT JOIN user_subscriptions us ON u.id = us.user_id AND us.is_active = 1
                    LEFT JOIN plans p ON us.plan_id = p.id
                    WHERE ak.key_id = %s AND ak.secret_key = %s AND ak.is_active = 1
                """, (api_key, secret_key))
                
                result = cursor.fetchone()
                if not result:
                    raise HTTPException(status_code=401, detail="Invalid API key or secret key")
                
                return {
                    'api_key_id': result[0],
                    'user_id': result[1],
                    'key_name': result[2],
                    'is_active': result[3],
                    'rate_limit_per_minute': result[4],
                    'rate_limit_per_day': result[5],
                    'usage_count': result[6],
                    'last_used_at': result[7],
                    'user_email': result[8],
                    'plan_id': result[9],
                    'plan_name': result[10],
                    'max_requests_per_month': result[11]
                }
    except Exception as e:
        print(f"API 키 검증 오류: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

def verify_api_key_only(api_key: str) -> Dict[str, Any]:
    """
    API Key만으로 기본 검증 (클라이언트용)
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # API Key만으로 조회 (Secret Key는 제외)
                cursor.execute("""
                    SELECT ak.id, ak.user_id, ak.name, ak.is_active, ak.rate_limit_per_minute, 
                           ak.rate_limit_per_day, ak.usage_count, ak.last_used_at, ak.allowed_origins,
                           u.email, us.plan_id, p.name as plan_name, p.max_requests_per_month
                    FROM api_keys ak
                    JOIN users u ON ak.user_id = u.id
                    LEFT JOIN user_subscriptions us ON u.id = us.user_id AND us.is_active = 1
                    LEFT JOIN plans p ON us.plan_id = p.id
                    WHERE ak.key_id = %s AND ak.is_active = 1
                """, (api_key,))
                
                result = cursor.fetchone()
                if not result:
                    raise HTTPException(status_code=401, detail="Invalid API key")
                
                return {
                    'api_key_id': result[0],
                    'user_id': result[1],
                    'key_name': result[2],
                    'is_active': result[3],
                    'rate_limit_per_minute': result[4],
                    'rate_limit_per_day': result[5],
                    'usage_count': result[6],
                    'last_used_at': result[7],
                    'allowed_origins': result[8],
                    'user_email': result[9],
                    'plan_id': result[10],
                    'plan_name': result[11],
                    'max_requests_per_month': result[12]
                }
    except Exception as e:
        print(f"API 키 검증 오류: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

def verify_domain_access(api_key_info: Dict[str, Any], request_domain: str) -> bool:
    """
    API 키의 도메인 제한을 확인합니다.
    """
    try:
        allowed_domains = api_key_info.get('allowed_origins')
        
        # allowed_domains가 없거나 비어있으면 모든 도메인 허용
        if not allowed_domains:
            return True
        
        # JSON 문자열인 경우 파싱
        if isinstance(allowed_domains, str):
            try:
                allowed_domains = json.loads(allowed_domains)
            except (json.JSONDecodeError, TypeError):
                return True  # 파싱 실패 시 모든 도메인 허용
        
        # 도메인 목록이 비어있으면 모든 도메인 허용
        if not allowed_domains or len(allowed_domains) == 0:
            return True
        
        # 요청 도메인이 허용 목록에 있는지 확인
        # 정확한 매치 또는 서브도메인 매치 지원
        for allowed_domain in allowed_domains:
            if allowed_domain.startswith('*.'):
                # 와일드카드 서브도메인 매치 (예: *.example.com)
                domain_suffix = allowed_domain[2:]  # *. 제거
                if request_domain == domain_suffix or request_domain.endswith('.' + domain_suffix):
                    return True
            else:
                # 정확한 도메인 매치
                if request_domain == allowed_domain:
                    return True
        
        return False
    except Exception as e:
        print(f"도메인 검증 오류: {e}")
        return True  # 오류 시 허용 (보안보다는 가용성 우선)

def generate_captcha_token(api_key_info: Dict[str, Any], captcha_type: str, challenge_data: Dict[str, Any]) -> str:
    """
    캡차 토큰을 생성합니다. (일회성 사용)
    """
    try:
        # 토큰 생성
        token_id = secrets.token_hex(16)
        token_data = {
            'token_id': token_id,
            'api_key_id': api_key_info['api_key_id'],
            'user_id': api_key_info['user_id'],
            'captcha_type': captcha_type,
            'challenge_data': challenge_data,
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(minutes=10)).isoformat(),  # 10분 만료
            'is_used': False
        }
        
        # Redis 또는 DB에 토큰 저장 (여기서는 DB 사용)
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO captcha_tokens (token_id, api_key_id, user_id, captcha_type, 
                                              challenge_data, created_at, expires_at, is_used)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    token_id,
                    api_key_info['api_key_id'],
                    api_key_info['user_id'],
                    captcha_type,
                    json.dumps(challenge_data),
                    datetime.now(),
                    datetime.now() + timedelta(minutes=10),
                    False
                ))
                conn.commit()
        
        return token_id
    except Exception as e:
        print(f"토큰 생성 오류: {e}")
        raise HTTPException(status_code=500, detail="Token generation failed")

def verify_captcha_token(token_id: str, api_key_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    캡차 토큰을 검증하고 일회성 사용을 보장합니다.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 토큰 조회
                cursor.execute("""
                    SELECT token_id, api_key_id, user_id, captcha_type, challenge_data, 
                           created_at, expires_at, is_used
                    FROM captcha_tokens
                    WHERE token_id = %s AND api_key_id = %s
                """, (token_id, api_key_info['api_key_id']))
                
                result = cursor.fetchone()
                if not result:
                    raise HTTPException(status_code=400, detail="Invalid token")
                
                # 만료 확인
                if result['expires_at'] < datetime.now():
                    raise HTTPException(status_code=400, detail="Token expired")
                
                # 사용 여부 확인
                if result['is_used']:
                    raise HTTPException(status_code=400, detail="Token already used")
                
                # 토큰을 사용됨으로 표시 (일회성 보장)
                cursor.execute("""
                    UPDATE captcha_tokens 
                    SET is_used = 1, used_at = NOW()
                    WHERE token_id = %s
                """, (token_id,))
                conn.commit()
                
                return {
                    'token_id': result['token_id'],
                    'captcha_type': result['captcha_type'],
                    'challenge_data': json.loads(result['challenge_data']) if result['challenge_data'] else {},
                    'created_at': result['created_at'].isoformat(),
                    'expires_at': result['expires_at'].isoformat()
                }
    except HTTPException:
        raise
    except Exception as e:
        print(f"토큰 검증 오류: {e}")
        raise HTTPException(status_code=500, detail="Token verification failed")

def check_rate_limit(api_key_info: Dict[str, Any]) -> bool:
    """
    API 키의 사용량 제한을 확인합니다.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 분당 요청 수 확인
                cursor.execute("""
                    SELECT COUNT(*) FROM request_logs 
                    WHERE api_key_id = %s AND created_at >= DATE_SUB(NOW(), INTERVAL 1 MINUTE)
                """, (api_key_info['api_key_id'],))
                
                minute_count = cursor.fetchone()[0]
                if minute_count >= api_key_info['rate_limit_per_minute']:
                    return False
                
                # 일일 요청 수 확인
                cursor.execute("""
                    SELECT COUNT(*) FROM request_logs 
                    WHERE api_key_id = %s AND created_at >= DATE_SUB(NOW(), INTERVAL 1 DAY)
                """, (api_key_info['api_key_id'],))
                
                day_count = cursor.fetchone()[0]
                if day_count >= api_key_info['rate_limit_per_day']:
                    return False
                
                # 월간 요청 수 확인 (요금제 기준)
                if api_key_info['max_requests_per_month']:
                    cursor.execute("""
                        SELECT COUNT(*) FROM request_logs 
                        WHERE api_key_id = %s AND created_at >= DATE_SUB(NOW(), INTERVAL 1 MONTH)
                    """, (api_key_info['api_key_id'],))
                    
                    month_count = cursor.fetchone()[0]
                    if month_count >= api_key_info['max_requests_per_month']:
                        return False
                
                return True
    except Exception as e:
        print(f"사용량 제한 확인 오류: {e}")
        return False

async def log_api_usage(api_key_info: Dict[str, Any], request_data: Dict[str, Any]):
    """
    API 사용량을 로그에 기록합니다.
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # API 키 사용량 업데이트
                cursor.execute("""
                    UPDATE api_keys 
                    SET usage_count = usage_count + 1, last_used_at = NOW() 
                    WHERE id = %s
                """, (api_key_info['api_key_id'],))
                
                # 요청 로그 기록 제거 (미들웨어에서 처리)
                # cursor.execute("""
                #     INSERT INTO request_logs (api_key_id, user_id, endpoint, method, 
                #                             request_data, response_status, created_at)
                #     VALUES (%s, %s, %s, %s, %s, %s, NOW())
                # """, (
                #     api_key_info['api_key_id'],
                #     api_key_info['user_id'],
                #     '/api/next-captcha',
                #     'POST',
                #     json.dumps(request_data),
                #     200
                # ))
                
                # conn.commit()
                
                # 캡차 사용량 증가 (user_usage_tracking 테이블)
                await usage_service.increment_captcha_usage(api_key_info['user_id'])
                
    except Exception as e:
        print(f"API 사용량 로그 기록 오류: {e}")

@router.post("/next-captcha")
async def next_captcha(request: Request):
    """
    행동 분석 데이터를 받아 다음 캡차 타입을 결정합니다. (클라이언트용 - API Key만 사용)
    """
    try:
        # API 키 헤더에서 추출
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            raise HTTPException(status_code=401, detail="API key required")
        
        # API 키만으로 검증 (클라이언트용)
        api_key_info = verify_api_key_only(api_key)
        
        # 도메인 제한 확인
        request_domain = request.headers.get('origin', '').replace('https://', '').replace('http://', '')
        if not verify_domain_access(api_key_info, request_domain):
            raise HTTPException(status_code=403, detail="Domain not allowed for this API key")
        
        # 사용량 제한 확인
        if not check_rate_limit(api_key_info):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        # 요청 데이터 파싱
        request_data = await request.json()
        behavior_data = request_data.get('behavior_data', {})
        site_key = request_data.get('site_key', '')
        
        # 행동 분석 로직 (간단한 예시)
        # 실제로는 ML 서비스와 연동하여 봇 탐지 수행
        mouse_movements = behavior_data.get('mouseMovements', [])
        mouse_clicks = behavior_data.get('mouseClicks', [])
        
        # 간단한 봇 탐지 로직
        is_bot_detected = False
        confidence_score = 0.8
        
        if len(mouse_movements) < 10:
            is_bot_detected = True
            confidence_score = 0.3
        
        if len(mouse_clicks) < 2:
            is_bot_detected = True
            confidence_score = 0.2
        
        # 다음 캡차 타입 결정
        if is_bot_detected:
            next_captcha_type = 'imagecaptcha'
        else:
            # 랜덤하게 캡차 타입 선택
            import random
            captcha_types = ['imagecaptcha', 'handwritingcaptcha', 'abstractcaptcha']
            next_captcha_type = random.choice(captcha_types)
        
        # 캡차 토큰 생성
        challenge_data = {
            'captcha_type': next_captcha_type,
            'confidence_score': confidence_score,
            'is_bot_detected': is_bot_detected,
            'behavior_data': behavior_data
        }
        captcha_token = generate_captcha_token(api_key_info, next_captcha_type, challenge_data)
        
        # API 사용량 로그 기록
        await log_api_usage(api_key_info, request_data)
        
        # 응답 데이터
        response_data = {
            "success": True,
            "next_captcha": next_captcha_type,
            "captcha_type": next_captcha_type,
            "captcha_token": captcha_token,  # 일회성 토큰
            "confidence_score": confidence_score,
            "is_bot_detected": is_bot_detected,
            "ml_service_used": "basic_behavior_analysis",
            "api_key_info": {
                "key_name": api_key_info['key_name'],
                "usage_count": api_key_info['usage_count'] + 1,
                "plan_name": api_key_info['plan_name']
            }
        }
        
        return JSONResponse(content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"next-captcha API 오류: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/verify-handwriting")
async def verify_handwriting(request: Request):
    """
    필기 캡차 응답을 검증합니다.
    """
    try:
        # 요청 데이터 파싱
        request_data = await request.json()
        image_base64 = request_data.get('image_base64', '')
        
        if not image_base64:
            raise HTTPException(status_code=400, detail="Image data required")
        
        # API Key 검증 (헤더에서 추출)
        api_key = request.headers.get('X-API-Key', '')
        if not api_key:
            raise HTTPException(status_code=401, detail="API key required")
        
        # API Key 검증
        api_key_info = verify_api_key_only(api_key)
        
        # 사용량 제한 확인
        if not check_rate_limit(api_key_info):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        # 필기 캡차 검증 로직 (간단한 예시)
        # 실제로는 ML 서비스와 연동하여 필기 인식 수행
        is_valid = len(image_base64) > 100  # 간단한 검증 (실제로는 ML 모델 사용)
        
        # API 사용량 로그 기록
        await log_api_usage(api_key_info, {"action": "handwriting_verification"})
        
        # 응답 데이터
        response_data = {
            "success": is_valid,
            "score": 0.9 if is_valid else 0.0,
            "action": "handwriting_verification",
            "challenge_ts": datetime.now().isoformat(),
            "hostname": request.headers.get('host', ''),
            "api_key_info": {
                "key_name": api_key_info['key_name'],
                "usage_count": api_key_info['usage_count'] + 1,
                "plan_name": api_key_info['plan_name']
            }
        }
        
        return JSONResponse(content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"verify-handwriting API 오류: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/verify-captcha")
async def verify_captcha(request: Request):
    """
    캡차 응답을 검증합니다. (서버용 - Secret Key 필요)
    """
    try:
        # 요청 데이터 파싱
        request_data = await request.json()
        api_key = request_data.get('site_key', '')  # API Key
        secret_key = request_data.get('secret_key', '')  # Secret Key
        captcha_response = request_data.get('response', '')
        captcha_token = request_data.get('captcha_token', '')  # 일회성 토큰
        
        if not api_key or not secret_key:
            raise HTTPException(status_code=401, detail="API key and secret key required")
        
        if not captcha_token:
            raise HTTPException(status_code=400, detail="Captcha token required")
        
        # API Key와 Secret Key 함께 검증
        api_key_info = verify_api_key_with_secret(api_key, secret_key)
        
        # 사용량 제한 확인
        if not check_rate_limit(api_key_info):
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
        
        # 캡차 토큰 검증 (일회성 사용 보장)
        token_info = verify_captcha_token(captcha_token, api_key_info)
        
        # 캡차 검증 로직 (간단한 예시)
        # 실제로는 ML 서비스와 연동하여 검증 수행
        is_valid = len(captcha_response) > 0  # 간단한 검증
        
        # API 사용량 로그 기록
        await log_api_usage(api_key_info, request_data)
        
        # 응답 데이터
        response_data = {
            "success": is_valid,
            "score": 0.9 if is_valid else 0.0,
            "action": "captcha_verification",
            "challenge_ts": token_info['created_at'],
            "hostname": request.headers.get('host', ''),
            "token_info": {
                "token_id": token_info['token_id'],
                "captcha_type": token_info['captcha_type'],
                "used_once": True  # 일회성 사용 확인
            },
            "api_key_info": {
                "key_name": api_key_info['key_name'],
                "usage_count": api_key_info['usage_count'] + 1,
                "plan_name": api_key_info['plan_name']
            }
        }
        
        return JSONResponse(content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"verify-captcha API 오류: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
