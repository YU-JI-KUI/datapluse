#!/usr/bin/env python3
"""
密码哈希工具

用途：生成 bcrypt 哈希密码，用于手动向数据库插入用户记录
使用：uv run python tools/hash_password.py

输出的哈希值可直接插入 users.password_hash 字段。
"""
import sys
from pathlib import Path

# 确保可以 import passlib（需在项目根目录运行）
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from passlib.context import CryptContext

_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _ctx.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _ctx.verify(plain, hashed)


if __name__ == "__main__":
    import getpass

    print("=" * 50)
    print("Datapulse 密码哈希工具")
    print("=" * 50)

    if len(sys.argv) > 1:
        password = sys.argv[1]
    else:
        password = getpass.getpass("请输入密码（不会显示）: ")
        confirm  = getpass.getpass("再次输入确认: ")
        if password != confirm:
            print("[ERROR] 两次输入不一致")
            sys.exit(1)

    hashed = hash_password(password)
    print(f"\n✓ bcrypt 哈希:\n{hashed}\n")
    print("将此哈希值填入 SQL 语句的 password_hash 字段，例如：")
    print(f"  INSERT INTO users (id, username, password_hash, is_active, created_at, updated_at)")
    print(f"  VALUES (gen_random_uuid()::text, 'admin', '{hashed}', TRUE, NOW()::text, NOW()::text);")
