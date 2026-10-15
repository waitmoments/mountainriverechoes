# -*- coding: utf-8 -*-
"""傣音廊 · 打包主程序(PyInstaller onedir)
==========================================
产物: dist/DaiMusic/DaiMusic.exe  (双击即开, 曲库从同目录 data/ 读取)

为什么用 onedir 而不是 onefile:
- 曲库 29MB, onefile 每次启动都要解压到临时目录 -> 冷启动慢好几秒
- onedir 便于把曲库与资源放成外部文件, 安装后可直接替换/更新
"""
import os
import sys
import time
import shutil

import PyInstaller.__main__

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
SEP = os.pathsep
STAMP = time.strftime('%H%M%S')


def retire(path):
    """把旧产物改名而不是删除。

    PyInstaller 在 workpath / distpath 已存在时会整批删除几千个缓存文件,
    在受限环境下会被安全策略拦下导致构建失败。这里先把旧目录改名挪开,
    让 PyInstaller 每次都面对一个不存在的目录, 从而跳过删除步骤。
    """
    if os.path.isdir(path):
        try:
            os.rename(path, path + '_old' + STAMP)
            print('[build] 旧目录已挪开:', path)
        except OSError as e:
            print('[build] 挪开失败(继续):', path, e)

APP_NAME = 'DaiMusic'
LIB_SRC = r'D:\e16_傣族.json'

opts = [
    os.path.join(ROOT, 'launcher.py'),
    '--name', APP_NAME,
    '--onedir',
    '--noconsole',
    '--noconfirm',
    # 不用 --clean: 它会把 build/ 里几千个缓存文件整批删除, 在受限环境下会被安全策略拦下
    '--icon', os.path.join(ROOT, 'assets', 'ui', 'app.ico'),
    # 全部用绝对路径: 相对路径会按 cwd 解析, 被 build_all import 调用时 cwd 不可靠
    '--add-data', os.path.join(ROOT, 'ui') + SEP + 'ui',
    '--add-data', os.path.join(ROOT, 'assets', 'ui') + SEP + os.path.join('assets', 'ui'),
    '--hidden-import', 'flask',
    '--hidden-import', 'jinja2',
    '--hidden-import', 'werkzeug',
    '--hidden-import', 'markupsafe',
    '--hidden-import', 'itsdangerous',
    '--hidden-import', 'blinker',
    '--hidden-import', 'charset_normalizer',
    '--exclude-module', 'tkinter',
    '--exclude-module', 'PIL',
    '--exclude-module', 'numpy',
    '--exclude-module', 'matplotlib',
    '--exclude-module', 'yt_dlp',
    '--exclude-module', 'musicdl',
    '--exclude-module', 'test',
    '--exclude-module', 'unittest',
    '--distpath', os.path.join(ROOT, 'dist'),
    '--specpath', ROOT,
    '--workpath', os.path.join(ROOT, 'build', 'w' + STAMP),
]


def finish(out):
    """打包收尾: 曲库放 exe 同级 data/ (library.resolve_library_path 第 2 顺位命中) + 写说明.txt。

    build_all.py 以 import 方式复用本模块, 收尾逻辑也必须能共享, 否则安装包里会缺说明.txt。
    """
    dd = os.path.join(out, 'data')
    os.makedirs(dd, exist_ok=True)
    dst = os.path.join(dd, 'e16_傣族.json')
    if os.path.isfile(LIB_SRC):
        shutil.copy2(LIB_SRC, dst)
        print('[build] library -> %s (%.1f MB)' % (dst, os.path.getsize(dst) / 1048576.0))
    else:
        print('[build] !! 未找到曲库', LIB_SRC)

    # 顺手放一份使用说明
    with open(os.path.join(out, '说明.txt'), 'w', encoding='utf-8') as f:
        f.write('傣音廊 · 傣族音乐播放器  v1.2.2\n'
                '================================\n'
                'DaiMusic.exe  双击启动（会自动打开一个独立窗口）\n'
                'data/         曲库数据（e16_傣族.json，共 6063 首傣族歌曲）\n'
                'ui/           界面文件\n'
                'assets/       图片素材\n\n'
                '说明：\n'
                '1. 曲库已筛选为纯傣族歌曲，不含其他民族曲目。\n'
                '2. 曲目直链来自各大音乐平台的公开接口，播放时会自动续签；\n'
                '   极少数曲目源站已下架，会提示"音源已失效"并自动跳过。\n'
                '3. 需要联网播放。首次播放某首歌会有 0.3~1 秒的解析延迟。\n'
                '4. 右上角调色板按钮可切换 6 套傣族主题皮肤（孔雀绿/金傣/朱砂红/\n'
                '   夜澜/贝叶/织锦），选择会自动记忆。\n'
                '5. 收藏、歌单、播放记录保存在 %APPDATA%\\DaiMusic\\state.json。\n')


if __name__ == '__main__':
    print('[build] root =', ROOT)
    retire(os.path.join(ROOT, 'dist', APP_NAME))
    PyInstaller.__main__.run(opts)
    finish(os.path.join(ROOT, 'dist', APP_NAME))
    print('[build] done ->', os.path.join(ROOT, 'dist', APP_NAME))
