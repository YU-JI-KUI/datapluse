"""
初始管理员创建工具

用途：在全新数据库中交互式创建第一个管理员账号。
使用：python tools/seed_admin.py

前提：
  1. 已执行 database/init.sql 建表
  2. 已配置 config.yaml（DB 连接信息）
"""
import sys
from pathlib import Path

# 将 backend 目录加入 sys.path，支持从项目根或 backend/ 下运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> None:
    print("=== Datapulse 管理员初始化工具 ===")
    print()

    # ── 读取配置 ──────────────────────────────────────────────────────────────
    try:
        from config.settings import get_settings
        settings = get_settings()
    except Exception as e:
        print(f"读取配置失败：{e}")
        print("请确认 config.yaml 已正确配置。")
        sys.exit(1)

    # ── 初始化 DB ─────────────────────────────────────────────────────────────
    try:
        from storage.db import get_db, init_db
        init_db(settings.db_url)
        db = get_db()
    except Exception as e:
        print(f"数据库连接失败：{e}")
        print("请检查 config.yaml 中的 database 配置。")
        sys.exit(1)

    # ── 写入预置角色和默认数据集 ──────────────────────────────────────────────
    try:
        db.seed_defaults()
        print("✓ 预置角色和默认数据集已就绪")
    except Exception as e:
        print(f"初始化预置数据失败：{e}")
        sys.exit(1)

    # ── 显示已有用户，询问是否继续 ────────────────────────────────────────────
    existing_users = db.list_users()
    if existing_users:
        print(f"\n当前已有 {len(existing_users)} 个用户：")
        for u in existing_users:
            roles = ", ".join(u.get("roles", []))
            print(f"  - {u['username']} [{roles}]")
        print()
        cont = input("是否继续创建新用户？(y/N): ").strip().lower()
        if cont != "y":
            print("已取消。")
            sys.exit(0)

    # ── 录入管理员信息 ────────────────────────────────────────────────────────
    print("\n请输入新管理员信息：")

    username = input("用户名: ").strip()
    if not username:
        print("用户名不能为空")
        sys.exit(1)

    if db.get_user_by_username(username):
        print(f"用户名已存在：{username}")
        sys.exit(1)

    # 注意：Windows CMD 下 getpass 会卡住，直接用 input
    password = input("密码（输入时可见）: ").strip()
    if not password:
        print("密码不能为空")
        sys.exit(1)
    if len(password) < 6:
        print("密码至少 6 位")
        sys.exit(1)

    confirm = input("再次确认密码: ").strip()
    if password != confirm:
        print("两次密码不一致")
        sys.exit(1)

    email = input("邮箱（可留空）: ").strip() or ""

    # ── 创建管理员 ────────────────────────────────────────────────────────────
    try:
        user = db.create_user(
            username=username,
            password=password,
            email=email,
            role_names=["admin"],
        )
        print()
        print(f"✓ 管理员 '{user['username']}' 创建成功！")
        print(f"  ID: {user['id']}")
        print()
        print("现在可以启动服务并使用该账号登录：")
        print("  cd backend && python main.py")
    except Exception as e:
        print(f"创建管理员失败：{e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
