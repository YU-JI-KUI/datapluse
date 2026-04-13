"""
Datapulse 跨平台启动脚本（Windows / Linux / Mac 通用）

Windows 用法（CMD）：
    python start.py

Linux / Mac 用法：
    python start.py
    # 或直接使用 ./start.sh（需要已安装 uv）

依赖安装（内网环境，走私服）：
    pip install uv -i http://maven.paic.com.cn/repository/pypi/simple --trusted-host maven.paic.com.cn
"""

import os
import subprocess
import sys
from pathlib import Path

# ── 内网 pip 私服 ──────────────────────────────────────────────────────────────
INTERNAL_PIP_INDEX = "http://maven.paic.com.cn/repository/pypi/simple"
INTERNAL_PIP_HOST  = "maven.paic.com.cn"

# ─────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.resolve()
os.chdir(ROOT)

SEP = "=" * 42


def banner(msg: str) -> None:
    print(f"\n{SEP}\n  {msg}\n{SEP}")


def run(cmd: list[str], **kwargs) -> int:
    """运行子进程，实时打印输出，返回退出码。"""
    print(f">>> {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, **kwargs)
    return result.returncode


def check_env_file() -> None:
    if not (ROOT / ".env").exists():
        print("[ERROR] 未找到 .env 文件，请先配置：")
        print("  复制 .env.example 为 .env，然后填入数据库连接信息")
        sys.exit(1)


def ensure_venv() -> Path:
    """确保 .venv 存在并安装依赖，返回 Python 解释器路径。"""
    venv_dir = ROOT / ".venv"
    # Windows: .venv/Scripts/python.exe  |  Linux/Mac: .venv/bin/python
    python_bin = (
        venv_dir / "Scripts" / "python.exe"
        if sys.platform == "win32"
        else venv_dir / "bin" / "python"
    )

    # 检查 uv 是否可用
    uv_available = run(["uv", "--version"], capture_output=True) == 0

    if uv_available:
        banner("同步 Python 依赖（uv）")
        rc = run(["uv", "sync"])
        if rc != 0:
            # 内网环境：uv 可能无法访问默认源，尝试用内网 pip 手动安装
            print("[WARN] uv sync 失败，尝试使用内网 pip 安装依赖...")
            _install_with_pip(venv_dir, python_bin)
    else:
        print("[WARN] 未找到 uv，使用内网 pip 安装依赖...")
        _install_with_pip(venv_dir, python_bin)

    return python_bin


def _install_with_pip(venv_dir: Path, python_bin: Path) -> None:
    """内网环境兜底：用 venv + 内网 pip 安装依赖。"""
    if not python_bin.exists():
        print("[1/2] 创建虚拟环境...")
        run([sys.executable, "-m", "venv", str(venv_dir)])

    print("[2/2] 安装依赖（内网私服）...")
    rc = run([
        str(python_bin), "-m", "pip", "install", "-e", ".",
        "-i", INTERNAL_PIP_INDEX,
        "--trusted-host", INTERNAL_PIP_HOST,
        "--quiet",
    ])
    if rc != 0:
        print("[ERROR] 依赖安装失败，请检查内网私服连通性")
        sys.exit(1)


def start_server(python_bin: Path) -> None:
    banner("启动 Web 服务")
    print("访问地址 → http://localhost:8000\n")
    rc = run([
        str(python_bin), "-m", "uvicorn",
        "datapulse.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
    ])
    sys.exit(rc)


if __name__ == "__main__":
    banner("Datapulse 数据飞轮 - 启动中")
    check_env_file()
    python_bin = ensure_venv()
    start_server(python_bin)
