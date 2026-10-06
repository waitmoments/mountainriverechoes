#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
山河回响 · 傣族库 自动备份脚本
================================
本仓库用 sparse-checkout 只拉取了傣族(e16)相关的文件，其余 55 个民族库不在工作区。
因此**绝不能用 `git add -A` / `git commit -a`**——那会把其它民族库当作"删除"提交掉。

本脚本只提交与傣族数据维护相关的文件：
  - webui/ethnos_cache/e16_傣族.json       (傣族曲库主数据)
  - webui/ethnos_cache/han_汉族民间小调.json (汉族库，避免同名冲突时参考)
  - webui/ethnos_cache/index_snapshot.json  (索引快照)
  - 仓库根目录下的研究/资料 .md (排除 README.md / SKILL.md)
  - 以及 versions/ 自动归档的历史版本(随上面 json 一起被 git 跟踪)

用法：
  方式一：直接被 AI 入库脚本在写盘后调用（推荐，实现"改完即备份"）
  方式二：手动运行  python backup_dai.py   或双击 backup_dai.bat
注意：本脚本只做本地提交，不会 push 到远程。需要同步时请人工确认后 `git push`。
"""
import subprocess
import time
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 定位 git：优先用 PATH 中的 git，否则回退到常见安装位置（含 WorkBuddy 托管的 PortableGit），
# 使本脚本在用户终端与无 git-PATH 的沙箱环境都能正常提交。
def _resolve_git():
    in_path = shutil.which("git")
    if in_path:
        return in_path
    candidates = [
        r"C:\Users\dyh\.workbuddy\binaries\PortableGit\versions\1.2.0\cmd\git.exe",
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return "git"  # 最后回退，交由 subprocess 报错

GIT = _resolve_git()

# 只提交这些显式列出的文件，绝不碰其它民族库
TARGETS = [
    "webui/ethnos_cache/e16_傣族.json",
    "webui/ethnos_cache/han_汉族民间小调.json",
    "webui/ethnos_cache/index_snapshot.json",
]

# 根目录下的研究/资料文档（排除项目自带说明）
EXCLUDE_MD = {"README.md", "SKILL.md"}
for p in sorted(ROOT.glob("*.md")):
    if p.name not in EXCLUDE_MD:
        TARGETS.append(str(p.relative_to(ROOT)))

# versions/ 历史快照随主 json 一起被跟踪，无需单独列


def run(cmd):
    if cmd and cmd[0] == "git":
        cmd = [GIT] + cmd[1:]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def main():
    # 只 add 明确列出的文件；不存在的文件会被 git 忽略（no-op）
    # 注：根目录的研究/资料 .md 落在 sparse-checkout（仅拉取 e16 傣族相关文件）
    # 范围之外，普通 git add 会被拒绝；用 --sparse 允许将其一并纳入傣族资料备份。
    add_cmd = ["git", "add", "--sparse", "--"] + TARGETS
    r = run(add_cmd)
    if r.returncode != 0:
        print("[backup] git add 失败：\n", r.stderr)
        raise SystemExit(r.returncode)

    ts = time.strftime("%Y-%m-%d %H:%M")
    msg = f"chore: 自动备份傣族库与资料变更 {ts}"
    r = run(["git", "commit", "-m", msg])
    if r.returncode == 0:
        print(f"[backup] 已提交：{msg}")
        # 打印本次提交涵盖的文件
        print(r.stdout.strip())
    else:
        # 没有改动时 git commit 会返回非 0，属正常情况
        out = (r.stdout or r.stderr).strip()
        if "nothing to commit" in out:
            print("[backup] 没有需要备份的改动，跳过。")
        else:
            print("[backup] commit 提示：", out)


if __name__ == "__main__":
    main()
