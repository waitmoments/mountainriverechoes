# -*- coding: utf-8 -*-
"""傣音廊 · 安装程序
====================
一个自带 payload 的图形化安装向导:
  选择安装位置 -> 解压文件 -> 建开始菜单/桌面快捷方式 -> 写卸载注册表项

打包: PyInstaller --onefile --add-data "dist/DaiMusic;payload" installer.py
"""
import os
import sys
import queue
import shutil
import subprocess
import threading
import winreg
import tkinter as tk
from tkinter import filedialog, messagebox

APP_NAME = '傣音廊'
APP_ID = 'DaiMusic'
APP_VER = '1.2.2'
PUBLISHER = '山河回响 · 傣族曲库'
EXE = 'DaiMusic.exe'

C_BG = '#F5F7F8'
C_DARK = '#0B3B36'
C_BRAND = '#0E6E63'
C_GOLD = '#D9A441'
C_TX = '#1E2329'
C_TX2 = '#6A7280'
C_LINE = '#E1E6E9'

DEFAULT_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
                           'Programs', APP_ID)


def res(rel):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def payload_dir():
    for c in (res('payload'), os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dist', APP_ID)):
        if os.path.isdir(c):
            return c
    raise FileNotFoundError('安装包损坏: 缺少 payload 数据')


def run_hidden(args):
    flags = 0x08000000 if os.name == 'nt' else 0   # CREATE_NO_WINDOW
    return subprocess.run(args, creationflags=flags, capture_output=True, text=True)


def make_shortcut(lnk_path, target, workdir, icon):
    """用 WScript.Shell 建 .lnk。脚本落地为 UTF-8-BOM 的 .ps1, 规避中文路径的 -Command 编码问题。"""
    os.makedirs(os.path.dirname(lnk_path), exist_ok=True)
    ps1 = os.path.join(os.environ.get('TEMP', '.'), '_dai_lnk.ps1')
    body = (
        '$ws = New-Object -ComObject WScript.Shell\r\n'
        '$sc = $ws.CreateShortcut("%s")\r\n'
        '$sc.TargetPath = "%s"\r\n'
        '$sc.WorkingDirectory = "%s"\r\n'
        '$sc.IconLocation = "%s"\r\n'
        '$sc.Description = "%s · 傣族音乐播放器"\r\n'
        '$sc.Save()\r\n'
    ) % (lnk_path, target, workdir, icon, APP_NAME)
    with open(ps1, 'w', encoding='utf-8-sig') as f:
        f.write(body)
    run_hidden(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps1])
    try:
        os.remove(ps1)
    except OSError:
        pass


def write_uninstall_registry(install_dir):
    exe_path = os.path.join(install_dir, EXE)
    unins = os.path.join(install_dir, 'uninstall.exe')
    try:
        size = 0
        for root, _d, files in os.walk(install_dir):
            for fn in files:
                try:
                    size += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                              r'Software\Microsoft\Windows\CurrentVersion\Uninstall\\' + APP_ID)
        vals = [
            ('DisplayName', APP_NAME + ' · 傣族音乐播放器'),
            ('DisplayVersion', APP_VER),
            ('Publisher', PUBLISHER),
            ('InstallLocation', install_dir),
            ('DisplayIcon', exe_path),
            ('UninstallString', '"%s"' % unins),
            ('QuietUninstallString', '"%s" /S' % unins),
            ('URLInfoAbout', ''),
        ]
        for k, v in vals:
            winreg.SetValueEx(key, k, 0, winreg.REG_SZ, v)
        winreg.SetValueEx(key, 'NoModify', 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, 'NoRepair', 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, 'EstimatedSize', 0, winreg.REG_DWORD, int(size / 1024))
        winreg.CloseKey(key)
    except Exception:
        pass


def _desktop_link():
    return os.path.join(os.path.expanduser('~'), 'Desktop', APP_NAME + '.lnk')


def copy_payload(src, target, cb=None):
    files = []
    for root, _d, fs in os.walk(src):
        for fn in fs:
            p = os.path.join(root, fn)
            files.append((p, os.path.relpath(p, src)))
    total = sum(os.path.getsize(p) for p, _ in files) or 1
    done = 0
    for p, rel in files:
        dst = os.path.join(target, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(p, dst)
        done += os.path.getsize(p)
        if cb:
            cb(done / total * 0.85)
    return len(files)


def do_install(target, desktop=True, cb=None):
    """完整安装流程(向导与静默模式共用)。"""
    src = payload_dir()
    if cb:
        cb(0.02)
    n = copy_payload(src, target, cb)

    exe = os.path.join(target, EXE)
    icon = os.path.join(target, '_internal', 'assets', 'ui', 'app.ico')
    if not os.path.isfile(icon):
        icon = exe
    sm = os.path.join(os.environ.get('APPDATA', ''),
                      r'Microsoft\Windows\Start Menu\Programs', APP_NAME + '.lnk')
    make_shortcut(sm, exe, target, icon)
    if cb:
        cb(0.93)
    if desktop:
        make_shortcut(_desktop_link(), exe, target, icon)
    if cb:
        cb(0.97)
    write_uninstall_registry(target)
    if cb:
        cb(1.0)
    return n


class Installer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('%s 安装程序' % APP_NAME)
        self.configure(bg=C_BG)
        self.resizable(False, False)
        self.geometry('620x460')
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.q = queue.Queue()
        self.installing = False
        self._center()
        self._build_head()
        self._build_body()
        self._build_foot()
        self.after(80, self._poll)

    def _center(self):
        self.update_idletasks()
        w, h = 620, 460
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 3
        self.geometry('%dx%d+%d+%d' % (w, h, x, y))

    # ---------------- 顶部渐变头 ----------------
    def _build_head(self):
        h = 96
        cv = tk.Canvas(self, height=h, highlightthickness=0, bd=0)
        cv.pack(fill='x')
        steps = 60
        for i in range(steps):
            t = i / (steps - 1)
            r = int(11 + (18 - 11) * t)
            g = int(59 + (165 - 59) * t)
            b = int(54 + (148 - 54) * t)
            cv.create_rectangle(i * 620 / steps, 0, (i + 1) * 620 / steps + 1, h,
                                fill='#%02x%02x%02x' % (r, g, b), outline='')
        # 傣锦菱形点缀
        for k in range(14):
            x = 380 + k * 18
            cv.create_polygon(x, 78, x + 7, 85, x, 92, x - 7, 85,
                              fill='', outline='#EFD08C', width=1)
        icon = res(os.path.join('assets', 'ui', 'icon.png'))
        self._icon_img = None
        try:
            self._icon_img = tk.PhotoImage(file=icon)
            self._icon_img = self._icon_img.subsample(4, 4)
            cv.create_image(26, h // 2, image=self._icon_img, anchor='w')
        except Exception:
            pass
        cv.create_text(96, 34, text=APP_NAME, anchor='w', fill='#FFFFFF',
                       font=('Microsoft YaHei UI', 19, 'bold'))
        cv.create_text(98, 62, text='傣族音乐播放器 · %s 首傣歌' % '8751', anchor='w',
                       fill='#CDEBE5', font=('Microsoft YaHei UI', 10))
        tk.Frame(self, height=1, bg=C_LINE).pack(fill='x')

    # ---------------- 主体 ----------------
    def _build_body(self):
        f = tk.Frame(self, bg=C_BG)
        f.pack(fill='both', expand=True, padx=30, pady=(22, 0))
        self.body = f

        tk.Label(f, text='安装位置', bg=C_BG, fg=C_TX,
                 font=('Microsoft YaHei UI', 10, 'bold')).place(x=0, y=0)
        self.var_dir = tk.StringVar(value=DEFAULT_DIR)
        e = tk.Entry(f, textvariable=self.var_dir, font=('Microsoft YaHei UI', 10),
                     relief='solid', bd=1, bg='#FFFFFF', fg=C_TX)
        e.place(x=0, y=26, width=470, height=32)
        tk.Button(f, text='浏览…', command=self.browse, bg='#E8ECEE', fg=C_TX,
                  relief='flat', font=('Microsoft YaHei UI', 9), cursor='hand2').place(x=482, y=26, width=76, height=32)

        self.var_desktop = tk.BooleanVar(value=True)
        self.var_run = tk.BooleanVar(value=True)
        for i, (v, t) in enumerate([(self.var_desktop, '创建桌面快捷方式'),
                                    (self.var_run, '安装完成后立即启动')]):
            tk.Checkbutton(f, text=t, variable=v, bg=C_BG, fg=C_TX, activebackground=C_BG,
                           selectcolor='#FFFFFF', font=('Microsoft YaHei UI', 10),
                           cursor='hand2').place(x=0, y=76 + i * 28)

        # 进度区
        self.lb_stage = tk.Label(f, text='', bg=C_BG, fg=C_TX2, font=('Microsoft YaHei UI', 9))
        self.lb_stage.place(x=0, y=150)
        self.cv_bar = tk.Canvas(f, height=10, highlightthickness=0, bg='#E4E9EB')
        self.cv_bar.place(x=0, y=176, width=558, height=10)
        self.bar = self.cv_bar.create_rectangle(0, 0, 0, 10, fill=C_BRAND, outline='')
        self.lb_pct = tk.Label(f, text='', bg=C_BG, fg=C_TX2, font=('Microsoft YaHei UI', 9))
        self.lb_pct.place(x=0, y=192)

        self.lb_note = tk.Label(
            f, bg=C_BG, fg=C_TX2, justify='left', font=('Microsoft YaHei UI', 9),
            text=('安装后会创建开始菜单与桌面快捷方式；\n'
                  '曲库共 8751 首傣族音乐，播放时需要联网（自动续签各平台直链）。\n'
                  '卸载可在「设置 → 应用 → 已安装的应用」中完成。'))
        self.lb_note.place(x=0, y=228)

    def _build_foot(self):
        f = tk.Frame(self, bg=C_BG)
        f.pack(fill='x', side='bottom', pady=(0, 20), padx=30)
        self.btn_install = tk.Button(f, text='开始安装', command=self.start,
                                     bg=C_BRAND, fg='#FFFFFF', activebackground=C_DARK,
                                     activeforeground='#FFFFFF', relief='flat',
                                     font=('Microsoft YaHei UI', 11, 'bold'), cursor='hand2')
        self.btn_install.pack(side='right', ipadx=26, ipady=7)
        self.btn_cancel = tk.Button(f, text='取消', command=self.on_close,
                                    bg='#E8ECEE', fg=C_TX2, relief='flat',
                                    font=('Microsoft YaHei UI', 10), cursor='hand2')
        self.btn_cancel.pack(side='right', ipadx=18, ipady=6, padx=(0, 10))

    # ---------------- 交互 ----------------
    def browse(self):
        d = filedialog.askdirectory(title='选择安装位置', initialdir=os.path.dirname(DEFAULT_DIR))
        if d:
            self.var_dir.set(os.path.join(d, APP_ID))

    def on_close(self):
        if self.installing:
            if not messagebox.askyesno(APP_NAME, '正在安装，确定要退出吗？'):
                return
        self.destroy()

    def start(self):
        d = self.var_dir.get().strip().strip('"')
        if not d:
            messagebox.showwarning(APP_NAME, '请选择安装位置')
            return
        try:
            os.makedirs(d, exist_ok=True)
            t = os.path.join(d, '._dai_write_test')
            with open(t, 'w') as f:
                f.write('x')
            os.remove(t)
        except Exception as e:
            messagebox.showerror(APP_NAME, '该目录不可写：\n%s\n\n%s' % (d, e))
            return
        self.installing = True
        self.btn_install.config(state='disabled', text='安装中…')
        self.btn_cancel.config(state='disabled')
        threading.Thread(target=self._work, args=(d,), daemon=True).start()

    def _post(self, kind, **kw):
        self.q.put((kind, kw))

    # ---------------- 后台安装 ----------------
    def _work(self, target):
        try:
            src = payload_dir()
            files = []
            for root, _d, fs in os.walk(src):
                for fn in fs:
                    p = os.path.join(root, fn)
                    files.append((p, os.path.relpath(p, src)))
            total = sum(os.path.getsize(p) for p, _ in files) or 1

            self._post('stage', t='正在解压程序文件…')
            done = 0
            for p, rel in files:
                dst = os.path.join(target, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(p, dst)
                done += os.path.getsize(p)
                self._post('progress', v=done / total * 0.85)

            self._post('stage', t='正在创建快捷方式…')
            exe = os.path.join(target, EXE)
            icon = os.path.join(target, '_internal', 'assets', 'ui', 'app.ico')
            if not os.path.isfile(icon):
                icon = exe
            sm = os.path.join(os.environ.get('APPDATA', ''),
                              r'Microsoft\Windows\Start Menu\Programs', APP_NAME + '.lnk')
            make_shortcut(sm, exe, target, icon)
            self._post('progress', v=0.93)
            if self.var_desktop.get():
                dsk = os.path.join(os.path.expanduser('~'), 'Desktop', APP_NAME + '.lnk')
                make_shortcut(dsk, exe, target, icon)
            self._post('progress', v=0.97)

            self._post('stage', t='正在注册卸载信息…')
            write_uninstall_registry(target)
            self._post('progress', v=1.0)
            self._post('done', target=target, run=self.var_run.get())
        except Exception as e:
            import traceback
            self._post('error', msg='%s\n\n%s' % (e, traceback.format_exc()[-500:]))

    def _poll(self):
        try:
            while True:
                kind, kw = self.q.get_nowait()
                if kind == 'stage':
                    self.lb_stage.config(text=kw['t'])
                elif kind == 'progress':
                    v = max(0.0, min(1.0, kw['v']))
                    self.cv_bar.coords(self.bar, 0, 0, 558 * v, 10)
                    self.lb_pct.config(text='%.0f%%' % (v * 100))
                elif kind == 'done':
                    self._finish(kw['target'], kw['run'])
                elif kind == 'error':
                    self.installing = False
                    messagebox.showerror(APP_NAME, '安装失败：\n\n' + kw['msg'])
                    self.btn_install.config(state='normal', text='重试')
                    self.btn_cancel.config(state='normal')
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(80, self._poll)

    def _finish(self, target, run):
        self.installing = False
        self.cv_bar.coords(self.bar, 0, 0, 558, 10)
        self.lb_stage.config(text='安装完成', fg=C_BRAND)
        self.lb_pct.config(text='100%')
        self.btn_install.config(text='完成', state='normal', command=self.destroy)
        self.btn_cancel.config(text='关闭', state='normal', command=self.destroy)
        self.lb_note.config(text='%s 已安装到：\n%s\n\n可以从桌面或开始菜单启动；'
                                 '播放时需要联网。' % (APP_NAME, target))
        if run:
            try:
                subprocess.Popen([os.path.join(target, EXE)], cwd=target,
                                 creationflags=0x08000000)
            except Exception:
                pass


if __name__ == '__main__':
    try:
        argv = sys.argv[1:]
        if argv and argv[0].lower() in ('/s', '-s', '--silent'):
            # 静默安装:  setup.exe /S [目标目录] [/nodesktop]
            tgt = DEFAULT_DIR
            desk = True
            for a in argv[1:]:
                if a.lower() in ('/nodesktop', '--nodesktop'):
                    desk = False
                elif not a.startswith('/'):
                    tgt = a
            os.makedirs(tgt, exist_ok=True)
            n = do_install(tgt, desktop=desk, cb=lambda v: None)
            print('installed %d files -> %s' % (n, tgt))
            sys.exit(0)
        Installer().mainloop()
    except Exception as e:
        import traceback
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, '安装程序错误：\n%s\n\n%s'
                                             % (e, traceback.format_exc()[-600:]),
                                             '傣音廊', 0x10)
        except Exception:
            raise
