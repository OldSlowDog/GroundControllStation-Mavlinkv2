#!/usr/bin/env python3
"""
INAV Stellar GCS — 自动同步脚本

工作流程:
  1. 检查当前目录是否为 Git 仓库，仓库是否有远程源
  2. 记录上次同步时的提交哈希（保存在 CHANGELOG_revision.txt 中）
  3. 获取从上次同步到现在的 commit 日志
  4. 按约定自动分类变更、更新 CHANGELOG.md
  5. 暂存所有变更、提交、推送到远程仓库

定时运行（每日 20:00）：
  - 配合操作系统的定时任务（cron / 任务计划程序）或 Trae Schedule 功能运行
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── 路径 ─────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
REVISION_FILE = PROJECT_ROOT / "CHANGELOG_revision.txt"
CHANGELOG_FILE = PROJECT_ROOT / "CHANGELOG.md"
STATE_FILE = PROJECT_ROOT / "auto_sync_state.json"
TZ_OFFSET = "+08:00"  # Asia/Shanghai


# ── 辅助函数 ─────────────────────────────────────────────────────────────
def run_git(*args: str, cwd: Path = PROJECT_ROOT) -> str:
    """执行 git 命令并返回 stdout (strip)。失败时抛出 RuntimeError。"""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} 失败 (exit={result.returncode}):\n"
            f"{result.stderr.strip()}"
        )
    return result.stdout.strip()


def git_log_since(ref: str | None) -> list[dict]:
    """获取从 ref 到 HEAD 的 commit 列表。ref=None 则取全部历史。"""
    if ref:
        args = ["log", f"{ref}..HEAD", "--format=%H||%ai||%s", "--no-decorate"]
    else:
        args = ["log", "--format=%H||%ai||%s", "--no-decorate"]

    raw = run_git(*args)
    if not raw:
        return []

    commits = []
    for line in raw.split("\n"):
        parts = line.split("||", 2)
        if len(parts) == 3:
            commits.append(
                {"hash": parts[0], "date": parts[1], "subject": parts[2]}
            )
    return commits


def read_changelog() -> str:
    """读取现有的 CHANGELOG.md，不存在则返回空字符串。"""
    if CHANGELOG_FILE.exists():
        return CHANGELOG_FILE.read_text(encoding="utf-8")
    return ""


def write_changelog(content: str):
    """写入 CHANGELOG.md。"""
    CHANGELOG_FILE.write_text(content, encoding="utf-8")
    print(f"[OK] CHANGELOG.md 已更新")


def build_changelog_entry(commits: list[dict]) -> str:
    """
    根据 commit subject 关键字自动分类生成 changelog 条目。
    返回 markdown 片段。
    """
    categories = {
        "✨ Added": [],
        "🔧 Changed": [],
        "🐛 Fixed": [],
        "⚠️ Deprecated": [],
        "🗑 Removed": [],
        "🔒 Security": [],
        "🧹 Chore": [],
    }

    # 中英文关键词映射
    patterns = {
        "✨ Added": re.compile(
            r"^(add|新增|feat|feature|实现|支持|添加|增加|init|初始化|创建)", re.I
        ),
        "🔧 Changed": re.compile(
            r"^(change|变更|修改|refactor|重构|update|更新|优化|improve|改进|migrate|迁移)",
            re.I,
        ),
        "🐛 Fixed": re.compile(
            r"^(fix|修复|bugfix|hotfix|修正|解决|resolve|correct|patch)", re.I
        ),
        "⚠️ Deprecated": re.compile(r"^(deprecate|弃用|mark.*deprecated)", re.I),
        "🗑 Removed": re.compile(
            r"^(remove|删除|移除|清理|cleanup|drop|delete)", re.I
        ),
        "🔒 Security": re.compile(
            r"^(security|安全|cve|vulnerability|漏洞|permission|权限)", re.I
        ),
    }

    for c in commits:
        matched = False
        for cat, pat in patterns.items():
            if pat.search(c["subject"]):
                categories[cat].append(c)
                matched = True
                break
        if not matched:
            categories["🧹 Chore"].append(c)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"\n## [{today}]\n"]

    for cat, items in categories.items():
        if not items:
            continue
        lines.append(f"### {cat}")
        for item in items:
            msg = item["subject"]
            if len(msg) > 80:
                msg = msg[:77] + "..."
            lines.append(f"- {msg}")
        lines.append("")

    return "\n".join(lines).rstrip("\n")


def is_git_repo() -> bool:
    """检查当前目录是否是 git 仓库。"""
    try:
        run_git("rev-parse", "--git-dir")
        return True
    except RuntimeError:
        return False


def has_remote() -> bool:
    """检查是否有名为 origin 的远程仓库。"""
    try:
        output = run_git("remote", "-v")
        return "origin" in output
    except RuntimeError:
        return False


# ── 主流程 ───────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  INAV Stellar GCS — Auto Sync")
    print(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 检查 Git 环境
    if not is_git_repo():
        print("[SKIP] 当前目录不是 Git 仓库，请先执行 git init")
        sys.exit(1)

    if not has_remote():
        print("[SKIP] 没有配置远程仓库 (origin)，请先添加远程仓库地址")
        sys.exit(1)

    print("[OK] Git 仓库和远程仓库均已就绪")

    # 2. 获取上次同步的 revision
    rev_ref = None
    if REVISION_FILE.exists():
        rev_ref = REVISION_FILE.read_text(encoding="utf-8").strip()
        print(f"[INFO] 上次同步 commit: {rev_ref[:12]}")
    else:
        print("[INFO] 首次同步，将记录全部历史")

    # 3. 获取 commit 列表
    commits = git_log_since(rev_ref)
    if not commits:
        print("[SKIP] 自上次同步以来无新的 commit")
        # 检查工作区是否有未提交的变更
        status = run_git("status", "--porcelain")
        if not status:
            print("[DONE] 工作区干净，无需更新")
            sync_finish()
            return
        print("[INFO] 检测到未提交的工作区变更")

    print(f"[INFO] 检测到 {len(commits)} 个新 commit")

    # 4. 更新 CHANGELOG
    existing = read_changelog()
    new_entry = build_changelog_entry(commits)

    # 在 "## [Unreleased]" 之后、"---" 之前插入新条目
    if "## [Unreleased]" in existing:
        # 插入到 Unreleased 部分之后
        insert_pos = existing.index("## [Unreleased]")
        unreleased_end = existing.index("---", insert_pos) if "---" in existing else len(existing)
        before = existing[:unreleased_end].rstrip() + "\n"
        after = existing[unreleased_end:]
        content = before + new_entry + "\n\n" + after
    else:
        # 在文件头部插入
        content = new_entry + "\n\n---\n\n" + existing

    write_changelog(content)

    # 5. Git add + commit + push
    print("[INFO] 暂存变更...")
    run_git("add", "-A")
    print("[OK] 暂存完成")

    # 检查是否有文件被暂存
    status = run_git("status", "--porcelain")
    if status:
        summary = f"auto-sync: update CHANGELOG ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
        run_git("commit", "-m", summary)
        print(f"[OK] 已提交: {summary}")

        print("[INFO] 推送到远程仓库...")
        run_git("push", "origin", "HEAD")
        print("[OK] 推送成功")
    else:
        print("[SKIP] 没有需要提交的变更")

    # 6. 记录当前 HEAD
    sync_finish()


def sync_finish():
    """流程结束时的收尾工作：记录当前 HEAD。"""
    head = run_git("rev-parse", "HEAD")
    REVISION_FILE.write_text(head, encoding="utf-8")
    state = {
        "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "revision": head[:12],
    }
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 同步完成，当前 HEAD: {head[:12]}")
    print("=" * 60)


if __name__ == "__main__":
    main()