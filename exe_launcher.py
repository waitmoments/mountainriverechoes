# -*- coding: utf-8 -*-
"""
山河回响 WebUI 启动器（供 PyInstaller 打包成 EXE）
==================================================
- 启动 Flask 服务(127.0.0.1:8766)
- 自动打开默认浏览器指向首页
- 冻结态下 BASE_DIR 由 webui.mountainriverechoes 自动切到 _MEIPASS
"""
import sys
import os
import time
import threading
import webbrowser

# 清空可能残留的代理变量: 沙箱/部分网络环境下存在指向 127.0.0.1:7897 的死代理,
# 会导致 Flask 进程内的续签/上游拉流请求挂死(前端播放卡在加载)。清空后改走直连。
for _pv in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_pv, None)


def _open_browser():
    time.sleep(2.5)
    try:
        from webui.mountainriverechoes import HOST, PORT
        webbrowser.open(f"http://{HOST}:{PORT}/")
    except Exception:
        pass


def main():
    # 避免 Windows 下默认 proactor 事件循环的某些阻塞(音乐客户端用到线程/子进程)
    if sys.platform == 'win32':
        try:
            import asyncio
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass

    from webui.mountainriverechoes import app, HOST, PORT
    threading.Thread(target=_open_browser, daemon=True).start()
    # use_reloader=False 在冻结态必关，否则会 spawn 子进程失败
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
