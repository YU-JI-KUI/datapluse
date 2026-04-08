"""
密码哈希工具

用途：生成 bcrypt 密码哈希，用于直接插入数据库或调试。
使用：uv run python tools/hash_password.py

注意：正常创建用户请使用 seed_admin.py 或 API，无需手动操作数据库。
"""
import sys
from pathlib import Path

# 将 backend 目录加入 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    try:
        from passlib.context import CryptContext
    except ImportError:
        print("错误：passlib 未安装。请运行: uv add passlib[bcrypt]")
        sys.exit(1)

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

    print("=== Datapluse 密码哈希生成工具 ===")
    print("输入明文密码，输出可直接写入数据库的 bcrypt 哈希。")
    print()

    password = input("请输入明文密码: ").strip()
    if not password:
        print("密码不能为空")
        sys.exit(1)

    hashed = pwd_ctx.hash(password)
    print()
    print(f"bcrypt 哈希：\n{hashed}")
    print()
    print("SQL INSERT 示例（替换 your_username 和上方哈希）：")
    print(f"""
INSERT INTO users (id, username, password_hash, is_active, created_at)
VALUES (
    gen_random_uuid(),
    'your_username',
    '{hashed}',
    true,
    NOW()
);
""")


if __name__ == "__main__":
    main()
