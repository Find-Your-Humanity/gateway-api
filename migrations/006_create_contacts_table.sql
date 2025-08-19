-- 문의사항 테이블 생성
CREATE TABLE IF NOT EXISTS contact_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    subject VARCHAR(255) NOT NULL COMMENT '문의 제목',
    contact VARCHAR(100) NOT NULL COMMENT '연락처',
    email VARCHAR(255) NOT NULL COMMENT '이메일',
    message TEXT NOT NULL COMMENT '문의 내용',
    attachment_filename VARCHAR(255) NULL COMMENT '첨부파일명',
    attachment_data LONGBLOB NULL COMMENT '첨부파일 데이터',
    status ENUM('unread', 'in_progress', 'resolved') DEFAULT 'unread' COMMENT '처리 상태',
    admin_response TEXT NULL COMMENT '관리자 답변',
    admin_id INT NULL COMMENT '처리한 관리자 ID',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '생성일시',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정일시',
    resolved_at TIMESTAMP NULL COMMENT '해결일시',
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),
    INDEX idx_email (email),
    FOREIGN KEY (admin_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='고객 문의사항';
