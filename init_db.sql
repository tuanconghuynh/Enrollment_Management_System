-- Tạo database (nếu chưa có)
CREATE DATABASE IF NOT EXISTS Admission_Management_System
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- Tạo user (chú ý dấu nháy do user có ký tự đặc biệt @)
CREATE USER IF NOT EXISTS 'vhtpt@hutech.edu.vn'@'%' IDENTIFIED BY 'VHTPT@hutech123';

-- Cấp toàn quyền cho database Admission_Management_System
GRANT ALL PRIVILEGES ON Admission_Management_System.* TO 'vhtpt@hutech.edu.vn'@'%';

-- Áp dụng thay đổi
FLUSH PRIVILEGES;
