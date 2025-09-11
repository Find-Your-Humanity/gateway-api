-- request_logs 테이블의 api_type ENUM 수정
ALTER TABLE request_logs MODIFY COLUMN api_type ENUM('handwriting', 'abstract', 'imagecaptcha', 'next_captcha') NULL DEFAULT NULL;
