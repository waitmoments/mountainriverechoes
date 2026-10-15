# -*- coding: utf-8 -*-
"""傣音廊 · 启动器
==================
1. 选一个空闲端口起本地服务(曲库常驻内存)
2. 用 Edge / Chrome 的 `--app` 模式开一个**独立无地址栏窗口**(像原生应用)
3. 窗口关闭即退出; 找不到 Chromium 内核浏览器时退回默认浏览器
"""
import os
import sys
import time
import socket
import threading
import subprocess
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_PORT = 8767
APP_TITLE = '傣音廊 · 傣族音乐'

CHROMIUM = [
    r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
    os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe'),
]


def msgbox(text, title='傣音廊', style=0x40):
    """无控制台环境下用系统弹窗提示(0x10 错误 / 0x40 信息)。"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, str(text), str(title), style)
    except Exception:
        print(text)


def port_free(port):
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(('127.0.0.1', port)) != 0


def alive(port):
    try:
        with urllib.request.urlopen('http://127.0.0.1:%d/api/health' % port, timeout=1.2) as r:
            return r.status == 200
    except Exception:
        return False


def find_browser():
    for p in CHROMIUM:
        if os.path.isfile(p):
            return p
    return None


def open_window(url, browser, profile_dir):
    """开一个独立 app 窗口, 返回 Popen(可为 None)。"""
    if not browser:
        return None
    args = [
        browser,
        '--app=' + url,
        '--user-data-dir=' + str(profile_dir),
        '--window-size=1380,880',
        '--no-first-run', '--no-default-browser-check',
        '--disable-features=Translate,TranslateUI,AutofillServerCommunication',
        '--disable-sync', '--no-service-autorun', '--disable-background-mode',
        '--disable-component-update', '--disable-default-apps',
        '--allow-file-access-from-files',
    ]
    try:
        flags = 0
        if os.name == 'nt':
            flags = 0x00000008  # DETACHED_PROCESS
        return subprocess.Popen(args, creationflags=flags,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print('[dai] 独立窗口启动失败:', e)
        return None


def main():
    # 已经在跑 -> 直接开窗口
    for p in range(BASE_PORT, BASE_PORT + 12):
        if not port_free(p) and alive(p):
            print('[dai] 检测到已在运行, 直接打开窗口 (port %d)' % p)
            b = find_browser()
            prof = Path(os.environ.get('APPDATA', os.path.expanduser('~'))) / 'DaiMusic' / 'browser'
            open_window('http://127.0.0.1:%d/' % p, b, prof)
            return

    port = next((p for p in range(BASE_PORT, BASE_PORT + 12) if port_free(p)), BASE_PORT)

    import app as appmod
    print('[dai] 曲库: %s (%d 首)' % (appmod.LIB.path, len(appmod.LIB.idx)))
    threading.Thread(target=appmod.serve, kwargs={'port': port}, daemon=True).start()

    t0 = time.time()
    while time.time() - t0 < 30 and not alive(port):
        time.sleep(0.25)
    if not alive(port):
        msgbox('本地服务启动超时。\n\n请确认杀毒软件未拦截本程序，然后重试。', '傣音廊 · 启动失败', 0x10)
        return

    url = 'http://127.0.0.1:%d/' % port
    print('[dai] 已就绪:', url)

    if os.environ.get('DAI_NO_WINDOW'):
        print('[dai] DAI_NO_WINDOW=1, 仅启动服务(调试用)')
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        return

    browser = find_browser()
    prof = Path(os.environ.get('APPDATA', os.path.expanduser('~'))) / 'DaiMusic' / 'browser'
    prof.mkdir(parents=True, exist_ok=True)
    proc = open_window(url, browser, prof)
    if proc is None:
        print('[dai] 未找到 Edge/Chrome, 使用默认浏览器')
        webbrowser.open(url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        return
    try:
        proc.wait()
    except KeyboardInterrupt:
        pass
    print('[dai] 窗口已关闭, 退出')


def run():
    try:
        main()
    except FileNotFoundError as e:
        msgbox('未找到曲库文件，程序无法启动。\n\n%s\n\n请重新安装。' % e, '傣音廊 · 缺少曲库', 0x10)
    except Exception as e:
        import traceback
        msgbox('启动时发生错误：\n\n%s\n\n%s' % (e, traceback.format_exc()[-800:]),
               '傣音廊 · 启动失败', 0x10)


if __name__ == '__main__':
    run()
