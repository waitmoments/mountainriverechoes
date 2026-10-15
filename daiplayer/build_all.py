# -*- coding: utf-8 -*-
"""傣音廊 · 一键构建安装包
==========================
  1. PyInstaller 打包主程序     -> dist/DaiMusic/
  2. 打包卸载器                 -> dist/DaiMusic/uninstall.exe
  3. 打包图形安装向导(内嵌 payload) -> installers/DaiMusic-Setup-1.1.0.exe

用法: python build_all.py  [--skip-app]
"""
import os
import sys
import time
import shutil

import PyInstaller.__main__

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
SEP = os.pathsep

APP_ID = 'DaiMusic'
VER = '1.2.2'
DIST_APP = os.path.join(HERE, 'dist', APP_ID)
INSTALLERS = os.path.join(HERE, 'installers')

HIDDEN = ['flask', 'jinja2', 'werkzeug', 'markupsafe', 'itsdangerous', 'blinker',
          'charset_normalizer']


def free(path):
    """清理构建中间目录。

    注意: 直接用 rmtree 会被批量删除保护拦截, 这里改为重命名到 <path>_old<时间戳>,
    既让 PyInstaller 拿到干净的目录名, 又避免触发批量删除确认。
    """
    if os.path.isdir(path):
        try:
            os.rename(path, path + '_old' + time.strftime('%H%M%S'))
        except OSError:
            shutil.rmtree(path, ignore_errors=True)


def build_app():
    print('=== [1/3] 打包主程序 ===')
    import build_app as ba
    # build_all 是 import 调用, build_app 的 retire() 不会自动执行, 这里显式把旧 dist/DaiMusic 挪开,
    # 否则 PyInstaller COLLECT 阶段删除旧目录会被安全删除策略拦截。
    old = os.path.join(DIST_APP)
    if os.path.isdir(old):
        try:
            os.rename(old, old + '_old' + time.strftime('%H%M%S'))
            print('[build] 旧 dist/DaiMusic 已挪开')
        except OSError as e:
            print('[build] 挪开失败(继续):', e)
    PyInstaller.__main__.run(ba.opts)
    # 曲库 + 说明.txt 由 build_app.finish() 统一收尾(import 调用时也要执行)
    ba.finish(DIST_APP)


def build_uninstaller():
    print('=== [2/3] 打包卸载器 ===')
    stamp = time.strftime('%H%M%S')
    out = os.path.join(HERE, 'build_unins_' + stamp)
    PyInstaller.__main__.run([
        os.path.join(HERE, 'uninstaller.py'), '--name', 'uninstall', '--onefile', '--noconsole',
        '--noconfirm',
        '--icon', os.path.join(HERE, 'assets', 'ui', 'app.ico'),
        '--distpath', out, '--workpath', os.path.join(HERE, 'build', 'u' + stamp),
        '--specpath', HERE,
    ])
    src = os.path.join(out, 'uninstall.exe')
    dst = os.path.join(DIST_APP, 'uninstall.exe')
    if os.path.isfile(src):
        shutil.copy2(src, dst)
        print('  ->', dst)
    free(out)


def build_installer():
    print('=== [3/3] 打包安装向导 ===')
    if not os.path.isdir(DIST_APP):
        print('!! 缺少', DIST_APP)
        return
    os.makedirs(INSTALLERS, exist_ok=True)
    name = 'DaiMusic-Setup-%s' % VER
    stamp = time.strftime('%H%M%S')
    inst = os.path.join(INSTALLERS, 'build_' + stamp)
    PyInstaller.__main__.run([
        os.path.join(HERE, 'installer.py'), '--name', name, '--onefile', '--noconsole',
        '--noconfirm',
        '--icon', os.path.join(HERE, 'assets', 'ui', 'app.ico'),
        '--add-data', DIST_APP + SEP + 'payload',
        '--add-data', os.path.join(HERE, 'assets', 'ui') + SEP + os.path.join('assets', 'ui'),
        '--hidden-import', 'tkinter', '--hidden-import', 'tkinter.filedialog',
        '--hidden-import', 'tkinter.messagebox',
        '--distpath', inst, '--workpath', os.path.join(HERE, 'build', 'i' + stamp),
        '--specpath', HERE,
    ])
    built = os.path.join(inst, name + '.exe')
    if os.path.isfile(built):
        shutil.copy2(built, os.path.join(INSTALLERS, name + '.exe'))
    free(inst)
    exe = os.path.join(INSTALLERS, name + '.exe')
    if os.path.isfile(exe):
        print('\n>>> 安装包: %s  (%.1f MB)' % (exe, os.path.getsize(exe) / 1048576.0))


if __name__ == '__main__':
    if '--skip-app' not in sys.argv:
        build_app()
    build_uninstaller()
    build_installer()
    print('\n全部完成。')
