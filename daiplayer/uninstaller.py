# -*- coding: utf-8 -*-
"""傣音廊 · 卸载程序
====================
删除安装目录 / 快捷方式 / 注册表项, 可选一并清除用户数据。

难点: 卸载器就住在要删的目录里, Windows 不允许删除正在运行的程序 ——
所以先把自身复制到 %TEMP% 再以 `--clean` 模式重新执行, 由临时副本去做删除。
"""
import os
import sys
import time
import shutil
import subprocess
import tempfile
import winreg
import tkinter as tk

APP_NAME = '傣音廊'
APP_ID = 'DaiMusic'

C_BG = '#F5F7F8'
C_BRAND = '#0E6E63'
C_TX = '#1E2329'
C_TX2 = '#6A7280'


def install_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def user_dir():
    return os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), APP_ID)


def flags():
    return 0x08000000 if os.name == 'nt' else 0


def rm_quiet(path):
    try:
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def remove_shortcuts():
    for p in (os.path.join(os.environ.get('APPDATA', ''),
                           r'Microsoft\Windows\Start Menu\Programs', APP_NAME + '.lnk'),
              os.path.join(os.path.expanduser('~'), 'Desktop', APP_NAME + '.lnk'),
              os.path.join(os.path.expanduser('~'), 'OneDrive', 'Desktop', APP_NAME + '.lnk')):
        rm_quiet(p)


def remove_registry():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER,
                         r'Software\Microsoft\Windows\CurrentVersion\Uninstall\\' + APP_ID)
    except OSError:
        pass


# ---------------------------------------------------------------- 临时副本模式
def clean_mode(target):
    time.sleep(1.5)
    remove_shortcuts()
    remove_registry()
    shutil.rmtree(target, ignore_errors=True)
    # 延迟删除自己(临时副本)
    me = sys.executable if getattr(sys, 'frozen', False) else __file__
    subprocess.Popen('cmd /c ping -n 3 127.0.0.1 > nul & del /f /q "%s"' % me,
                     shell=True, creationflags=flags())


# ---------------------------------------------------------------- 界面
def gui():
    d = install_dir()
    root = tk.Tk()
    root.title('卸载 ' + APP_NAME)
    root.configure(bg=C_BG)
    root.resizable(False, False)
    w, h = 460, 300
    root.geometry('%dx%d+%d+%d' % (w, h, (root.winfo_screenwidth() - w) // 2,
                                   (root.winfo_screenheight() - h) // 3))

    tk.Label(root, text='卸载 ' + APP_NAME, bg=C_BG, fg=C_TX,
             font=('Microsoft YaHei UI', 15, 'bold')).pack(anchor='w', padx=26, pady=(24, 6))
    tk.Label(root, text='将从以下位置移除程序文件：', bg=C_BG, fg=C_TX2,
             font=('Microsoft YaHei UI', 9)).pack(anchor='w', padx=26)
    tk.Label(root, text=d, bg=C_BG, fg=C_TX, wraplength=400, justify='left',
             font=('Microsoft YaHei UI', 9)).pack(anchor='w', padx=26, pady=(2, 14))

    var_data = tk.BooleanVar(value=False)
    tk.Checkbutton(root, text='同时删除我的收藏、歌单与播放记录', variable=var_data,
                   bg=C_BG, fg=C_TX, activebackground=C_BG, selectcolor='#FFFFFF',
                   font=('Microsoft YaHei UI', 10), cursor='hand2').pack(anchor='w', padx=24)

    box = tk.Frame(root, bg=C_BG)
    box.pack(side='bottom', fill='x', padx=26, pady=18)

    def do():
        if var_data.get():
            rm_quiet(user_dir())
        me = sys.executable if getattr(sys, 'frozen', False) else __file__
        tmp = os.path.join(tempfile.gettempdir(), 'dai_unins_%d.exe' % os.getpid())
        try:
            shutil.copy2(me, tmp)
            subprocess.Popen([tmp, '--clean', d], creationflags=flags())
        except Exception:
            # 复制失败 -> 尽力而为: 直接清目录(自己可能删不掉, 留待下次)
            remove_shortcuts()
            remove_registry()
            shutil.rmtree(d, ignore_errors=True)
        root.destroy()

    ok = tk.Button(box, text='卸载', command=do, bg='#C8452F', fg='#FFFFFF',
                   activebackground='#9E3522', activeforeground='#FFFFFF', relief='flat',
                   font=('Microsoft YaHei UI', 11, 'bold'), cursor='hand2')
    ok.pack(side='right', ipadx=26, ipady=6)
    tk.Button(box, text='取消', command=root.destroy, bg='#E8ECEE', fg=C_TX2, relief='flat',
              font=('Microsoft YaHei UI', 10), cursor='hand2').pack(side='right', ipadx=18, ipady=5, padx=(0, 10))

    root.mainloop()


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == '--clean':
        clean_mode(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == '/S':   # 静默卸载
        t = install_dir()
        remove_shortcuts()
        remove_registry()
        me = sys.executable if getattr(sys, 'frozen', False) else __file__
        tmp = os.path.join(tempfile.gettempdir(), 'dai_unins_%d.exe' % os.getpid())
        try:
            shutil.copy2(me, tmp)
            subprocess.Popen([tmp, '--clean', t], creationflags=flags())
        except Exception:
            shutil.rmtree(t, ignore_errors=True)
    else:
        gui()
