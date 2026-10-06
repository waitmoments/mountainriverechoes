# -*- coding: utf-8 -*-
"""
山河回响 · 傣族(e16)曲库 数据维护脚本（按 SKILL.md 入库规范）
==============================================================
安全红线（见 SKILL.md §5.1.4 / §8）：
  - 仅【追加】新曲目到现有 tracks，绝不调用 _ethnos_payload 全量重建，
    以免覆盖现有 6786 首里可能的人工标签（singers 字段）。
  - 写盘前先 cp 备份；使用主程序 _atomic_write_json（自带 versions/ 归档）。
  - 网易云一律只用官方 v1 (_parsewithofficialapiv1)，严禁 _parsewiththirdpartapis。
  - 清空死代理环境变量，避免撞 127.0.0.1:7897。
  - 直接 import 主程序函数落盘，不另起 tools_*_ingest.py 副本。
  - 写盘后自动调用 backup_dai.py 提交到本地 git（仅傣族相关文件，不碰其它民族库）。

用法：
  python ingest_dai.py            # 正式运行（搜索+去重+追加+备份）
  python ingest_dai.py --dry-run  # 只搜索/去重/统计，不写盘不提交
"""
import sys
import os
import json
import time
import argparse

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# 清空可能残留的代理变量（SKILL.md §8.2：避免死代理 127.0.0.1:7897）
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)

import musicdl.musicdl as musicdl  # noqa: E402
from webui.mountainriverechoes import (  # noqa: E402
    _cache_path, _dedup_key, _ethnos_payload, ETHNIC_BY_KEY,
    _atomic_write_json, _ethnos_get_client, _search_ethnos_keyword,
)
from musicdl.modules import SongInfo  # noqa: E402

GROUP_KEY = 'e16'          # 傣族
ARTIST_LIMIT = 12          # 每位艺人最多保留的候选（按分数）
QUERY_INTERVAL = 1.5       # 关键词间节流，避免源站限流

# 傣族核心检索词（聚焦版，控制时长）：代表曲目 + 代表艺人 + 关键体裁/乐器
# 说明：傣族库已有 6786 首，泛型词重复率极高；本列表偏重"可能缺失的艺人/曲目"，
#       以尽量补出真正新增的傣族音源。如需全量深挖，把 KEYWORDS 换回完整列表即可。
KEYWORDS = [
    # 代表曲目（补全可能缺失的版本）
    '月光下的凤尾竹', '有一个美丽的地方', '竹林深处', '多情的巴乌',
    '婚誓', '欢乐的泼水节', '金色的孔雀', '美丽的西双版纳', '傣族舞曲',
    # 代表艺人（补全可能缺失的傣族歌手/演奏家）
    '哏德全', '玉罕娇', '金小摆', '岩更', '刀美兰', '依养', '喊路', '岩宰',
    # 关键体裁 / 乐器
    '赞哈', '象脚鼓', '傣剧',
]


def load_existing(path):
    """读取现有库：返回 (去重键集合, 曲目数, 完整 payload dict)。"""
    if not path.exists():
        return set(), 0, {}
    d = json.loads(path.read_text(encoding='utf-8'))
    keys = set()
    for t in d.get('tracks') or []:
        sd = t.get('_song') or {}
        try:
            s = SongInfo.fromdict(sd)
            if s.song_name:
                keys.add(_dedup_key(s))
        except Exception:
            pass
    return keys, d.get('count', len(d.get('tracks') or [])), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='只统计不写盘')
    args = ap.parse_args()

    info = ETHNIC_BY_KEY[GROUP_KEY]
    path = _cache_path(GROUP_KEY)
    existing_keys, before_count, existing_payload = load_existing(path)
    existing_tracks = existing_payload.get('tracks') or []
    print(f"[init] 傣族库当前 {before_count} 首，去重键 {len(existing_keys)} 个")

    # 备份当前库文件（额外手动备份，超越 versions/ 轮转上限）
    if not args.dry_run and path.exists():
        bak = path.with_suffix('.bak-pre-ingest-' + str(int(time.time())) + path.suffix)
        import shutil
        shutil.copy2(path, bak)
        print(f"[backup] 已手动备份旧库 -> {bak.name}")

    client = _ethnos_get_client()
    seen_new = set()
    new_songs = []
    for kw in KEYWORDS:
        try:
            songs = _search_ethnos_keyword(client, kw)
        except Exception as e:
            print(f"[warn] 搜索 '{kw}' 失败: {e}")
            songs = []
        added_this = 0
        for s in songs:
            if not getattr(s, 'song_name', None):
                continue
            k = _dedup_key(s)
            if k in existing_keys or k in seen_new:
                continue
            seen_new.add(k)
            new_songs.append(s)
            added_this += 1
        print(f"[search] '{kw}': 命中 {len(songs)} 首，新增候选 {added_this} 首（累计 {len(new_songs)}）")
        time.sleep(QUERY_INTERVAL)

    if not new_songs:
        print("[result] 没有发现需要补录的新曲目（现有库已覆盖这些关键词）。")
        if not args.dry_run:
            # 仍提交一次（可能无改动，backup 会判定跳过）
            os.system(f'"{sys.executable}" "{os.path.join(PROJECT_ROOT, "backup_dai.py")}"')
        return

    if args.dry_run:
        print(f"[dry-run] 拟新增 {len(new_songs)} 首，写盘已跳过。")
        return

    # 仅用 _ethnos_payload 格式化【新歌】，不重建旧歌（杜绝覆盖人工标签）
    new_payload = _ethnos_payload(info, GROUP_KEY, new_songs, partial=False)
    new_tracks = new_payload.get('tracks') or []

    merged = existing_tracks + new_tracks
    # 在现有完整 payload 上追加，保留原有 cover/name/kws/key 等全部元数据
    out = dict(existing_payload)
    out['tracks'] = merged
    out['count'] = len(merged)
    out['partial'] = False
    out['built_at'] = time.time()
    # 兜底字段（正常情况下已存在，不会触发）
    out.setdefault('name', f"{info['name']} · 民族音乐")
    out.setdefault('group', info['name'])
    out.setdefault('key', GROUP_KEY)
    out.setdefault('sources', new_payload.get('sources', []))

    _atomic_write_json(path, out)
    after = len(merged)
    print(f"[write] 追加 {len(new_tracks)} 首，库内总计 {after} 首（原 {before_count}）")

    # 自动备份到本地 git（只提交傣族相关文件）
    rc = os.system(f'"{sys.executable}" "{os.path.join(PROJECT_ROOT, "backup_dai.py")}"')
    print(f"[backup] 备份脚本退出码 {rc}")


if __name__ == '__main__':
    main()
