# -*- coding: utf-8 -*-
"""
山河回响 · 打包 WebUI 为单文件 EXE (PyInstaller)
================================================
产物: dist/MountainRiverEchoes.exe (便携, 双击即开 http://127.0.0.1:8766)
数据随包解压到 _MEIPASS: webui/templates + webui/ethnos_cache(e16 傣族库等)

用法:
  python build_exe.py
说明:
  - 用 --collect-all 收纳 musicdl / yt_dlp 全部子模块(含动态导入的源客户端)
  - 补充隐藏导入, 规避冻结态常见 ModuleNotFoundError
  - 入口 exe_launcher.py 会自开浏览器
"""
import os
import sys

import PyInstaller.__main__  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

SEP = os.pathsep  # Windows 用 ';'

opts = [
    'exe_launcher.py',
    '--name', 'MountainRiverEchoes',
    '--onefile',
    '--noconsole',
    '--noconfirm',
    '--distpath', 'dist',
    '--workpath', 'build',
    # 数据文件: 模板 + 民族曲库(含 e16_傣族.json)
    '--add-data', os.path.join('webui', 'templates') + SEP + os.path.join('webui', 'templates'),
    '--add-data', os.path.join('webui', 'ethnos_cache') + SEP + os.path.join('webui', 'ethnos_cache'),
    # 整体收纳复杂包
    '--collect-all', 'musicdl',
    '--collect-all', 'yt_dlp',
    # 显式隐藏导入(冻结态易丢)
    '--hidden-import', 'flask',
    '--hidden-import', 'markupsafe',
    '--hidden-import', 'jinja2',
    '--hidden-import', 'werkzeug',
    '--hidden-import', 'itsdangerous',
    '--hidden-import', 'blinker',
    '--hidden-import', 'av',
    '--hidden-import', 'pywidevine',
    '--hidden-import', 'curl_cffi',
    '--hidden-import', 'pycryptodomex',
    '--hidden-import', 'pycryptodome',
    '--hidden-import', 'lxml',
    '--hidden-import', 'mutagen',
    '--hidden-import', 'tinytag',
    '--hidden-import', 'm3u8',
    '--hidden-import', 'prompt_toolkit',
    '--hidden-import', 'rich',
    '--hidden-import', 'emoji',
    '--hidden-import', 'bleach',
    '--hidden-import', 'beautifulsoup4',
    '--hidden-import', 'ytmusicapi',
    '--hidden-import', 'aigpy',
    '--hidden-import', 'json_repair',
    '--hidden-import', 'pathvalidate',
    '--hidden-import', 'prettytable',
    '--hidden-import', 'websocket',
    '--hidden-import', 'websocket_client',
    '--hidden-import', 'brotli',
    '--hidden-import', 'platformdirs',
    '--hidden-import', 'filetype',
    '--hidden-import', 'puremagic',
    '--hidden-import', 'typing_extensions',
    '--hidden-import', 'tabulate',
    '--hidden-import', 'orjson',
    '--hidden-import', 'requests',
    '--hidden-import', 'cryptography',
    '--hidden-import', 'fake_useragent',
    '--hidden-import', 'nodejs_wheel',
]

if __name__ == '__main__':
    print('[build] chdir ->', ROOT)
    PyInstaller.__main__.run(opts)
    print('[build] done')
