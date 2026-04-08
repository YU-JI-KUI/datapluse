#!/usr/bin/env python3
"""
管理员账号初始化工具

用途：在 DB 中没有任何用户时，交互式创建第一个管理员账号
使用：uv run python tools/seed_admin.py

前提：config.yaml 中 database 节点已配置正确的数据库连接信息。
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from config.settings import get_settings
from storage.db import get_db, init_db

if __name__ == "__main__":
    print("=" * 50)
    print("Datapulse 管理员账号初始化")
    print("=" * 50)

    settings = get_settings()
    try:
        init_db(settings.db_url)
    except Exception as e:
        print(f"[ERROR] 数据库连接失败：{e}")
        sys.exit(1)

    db = get_db()

    # 确保预置角色和默认数据集存在
    db.seed_defaults()

    # 检查是否已有用户
    users = db.list_users()
    if users:
        print(f"[INFO] 数据库中已有 {len(users)} 个用户，无需重新初始化。")
        print("已有用户：" + ", ".join(u["username"] for u in users))
        sys.exit(0)

    print("\n当前数据库中没有用户，请创建第一个管理员账号：")
    username = input("用户名 [admin]: ").strip() or "admin"
    email    = input("邮箱（可选）: ").strip()
    password = getpass.getpass("密码（不会显示）: ")
    confirm  = getpass.getpass("再次输入密码: ")

    if password != confirm:
        print("[ERROR] 两次密码不一致")
        sys.exit(1)

    if len(password) < 6:
        print("[ERROR] 密码至少 6 位")
        sys.exit(1)

    try:
        user = db.create_user(username=username, password=password,
                              email=email, role_names=["admin"])
        print(f"\n✓ 管理员账号创建成功：{user['username']} (id={user['id']})")
        print("现在可以启动服务并使用此账号登录。")
    except Exception as e:
        print(f"[ERROR] 创建失败：{e}")
        sys.exit(1)
