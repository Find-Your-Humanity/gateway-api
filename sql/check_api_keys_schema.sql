-- api_keys 테이블 구조 확인
DESCRIBE api_keys;

-- api_keys 테이블의 인덱스 확인
SHOW INDEX FROM api_keys;

-- api_keys 테이블의 외래키 제약조건 확인
SELECT 
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = DATABASE()
AND TABLE_NAME = 'api_keys';
