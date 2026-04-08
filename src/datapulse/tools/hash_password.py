"""
密码哈希工具

用途：生成 bcrypt 密码哈希，用于直接插入数据库或调试。
使用：python tools/hash_password.py

注意：正常创建用户请使用 seed_admin.py 或 API，无需手动操作数据库。
"""

import sys

try:
    import bcrypt
except ImportError:
    print("错误：bcrypt 未安装。")
    print(
        "请运行：pip install bcrypt -i http://maven.paic.com.cn/repository/pypi/simple --trusted-host maven.paic.com.cn"
    )
    sys.exit(1)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def main() -> None:
    print("=== Datapulse 密码哈希生成工具 ===")
    print("输入明文密码，输出可直接写入数据库的 bcrypt 哈希。")
    print()

    password = input("请输入明文密码: ").strip()
    if not password:
        print("密码不能为空")
        sys.exit(1)

    hashed = hash_password(password)

    print()
    print("bcrypt 哈希：")
    print(hashed)
    print()
    print("手动插入 SQL 示例（替换 your_username）：")
    print(f"""
INSERT INTO users (username, password_hash, is_active, created_at, updated_at)
VALUES ('your_username', '{hashed}', TRUE, NOW()::text, NOW()::text);

-- 授予 admin 角色：
INSERT INTO user_roles (user_id, role_id, created_at)
SELECT u.id, r.id, NOW()::text
FROM users u, roles r
WHERE u.username = 'your_username' AND r.name = 'admin';
""")


if __name__ == "__main__":
    main()
