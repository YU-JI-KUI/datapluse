"""
初始管理员创建工具

用途：在全新数据库中交互式创建第一个管理员账号。
使用：uv run python tools/seed_admin.py

前提：
  1. 已执行 database/init.sql 建表
  2. 已配置 config.yaml（DB 连接信息）
"""
import sys
from pathlib import Path

# 将 backend 目录加入 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    print("=== Datapluse 管理员初始化工具 ===")
    print()

    # 读取配置
    try:
        from config.settings import get_settings
        settings = get_settings()
    except Exception as e:
        print(f"读取配置失败：{e}")
        print("请确认 config.yaml 已正确配置。")
        sys.exit(1)

    # 初始化 DB
    try:
        from storage.db import init_db, get_db
        init_db(settings.db_url)
        db = get_db()
    except Exception as e:
        print(f"数据库连接失败：{e}")
        print("请检查 config.yaml 中的 database 配置。")
        sys.exit(1)

    # 写入预置角色和默认数据集
    try:
        db.seed_defaults()
        print("✓ 预置角色和默认数据集已就绪")
    except Exception as e:
        print(f"初始化预置数据失败：{e}")
        sys.exit(1)

    # 检查是否已有用户
    existing_users = db.list_users()
    if existing_users:
        print(f"当前已有 {len(existing_users)} 个用户：")
        for u in existing_users:
            roles = ", ".join(u.get("roles", []))
            print(f"  - {u['username']} [{roles}]")
        print()
        cont = input("是否继续创建新用户？(y/N): ").strip().lower()
        if cont != "y":
            print("已取消。")
            sys.exit(0)

    # 录入管理员信息
    print()
    print("请输入新管理员信息：")
    username = input("用户名: ").strip()
    if not username:
        print("用户名不能为空")
        sys.exit(1)

    import getpass
    password = getpass.getpass("密码: ").strip()
    if not password:
        print("密码不能为空")
        sys.exit(1)

    confirm = getpass.getpass("再次确认密码: ").strip()
    if password != confirm:
        print("两次密码不一致")
        sys.exit(1)

    display_name = input("显示名称（可留空）: ").strip() or None

    # 创建管理员
    try:
        from passlib.context import CryptContext
        pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        password_hash = pwd_ctx.hash(password)

        user = db.create_user(
            username=username,
            password_hash=password_hash,
            display_name=display_name,
            role_name="admin",
            is_active=True,
        )
        print()
        print(f"✓ 管理员 '{user['username']}' 创建成功！")
        print(f"  ID: {user['id']}")
        print()
        print("现在可以启动服务并使用该账号登录：")
        print("  cd backend && uv run python main.py")
    except Exception as e:
        print(f"创建管理员失败：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
