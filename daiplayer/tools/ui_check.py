# -*- coding: utf-8 -*-
"""通过 CDP 截图 + 抓控制台错误, 用于 UI 自查。"""
import io, json, base64, time, sys, urllib.request

def w(*a):
    print(*a, flush=True)

# 本机回环必须绕开环境里的 HTTP_PROXY(否则 127.0.0.1 也会被塞进代理 -> 502)
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(_opener)

CDP = 'http://127.0.0.1:9222'
def http_json(path):
    with _opener.open(CDP + path, timeout=6) as r:
        return json.loads(r.read().decode('utf-8'))

# 等浏览器就绪
t0 = time.time()
tabs = None
while time.time() - t0 < 25:
    try:
        tabs = http_json('/json/list')
        if tabs:
            break
    except Exception:
        pass
    time.sleep(0.4)
if not tabs:
    w('CDP 不可达'); sys.exit(1)

pages = [t for t in tabs if t.get('type') == 'page' and str(t.get('url', '')).startswith('http')]
page = (pages or [t for t in tabs if t.get('type') == 'page'] or tabs)[0]
ws_url = page['webSocketDebuggerUrl']
w('tab:', page.get('url'), ws_url[:70])

import websocket
ws = websocket.create_connection(ws_url, timeout=40)
mid = [0]
logs = []

def send(method, params=None, wait=True):
    mid[0] += 1
    i = mid[0]
    ws.send(json.dumps({'id': i, 'method': method, 'params': params or {}}))
    if not wait:
        return None
    while True:
        m = json.loads(ws.recv())
        if m.get('method') == 'Runtime.consoleAPICalled':
            logs.append('[console.%s] %s' % (m['params'].get('type'),
                        ' '.join(str(x.get('value', x.get('description', ''))) for x in m['params'].get('args', []))))
        elif m.get('method') == 'Runtime.exceptionThrown':
            d = m['params']['exceptionDetails']
            logs.append('[EXC] %s %s' % (d.get('text'), (d.get('exception') or {}).get('description', '')[:400]))
        elif m.get('method') == 'Log.entryAdded':
            e = m['params']['entry']
            logs.append('[log.%s] %s %s' % (e.get('level'), e.get('text'), (e.get('url') or '')[:80]))
        if m.get('id') == i:
            return m.get('result', m)

send('Runtime.enable'); send('Log.enable'); send('Page.enable')
send('Emulation.setDeviceMetricsOverride',
     {'width': 1420, 'height': 940, 'deviceScaleFactor': 1, 'mobile': False})

def goto(url, wait_s=4.0):
    send('Page.navigate', {'url': url})
    time.sleep(wait_s)

def shot(path, full=False):
    r = send('Page.captureScreenshot', {'format': 'png', 'captureBeyondViewport': full})
    data = r.get('data')
    if not data:
        w('截图失败', r); return False
    with open(path, 'wb') as f:
        f.write(base64.b64decode(data))
    w('  saved', path)
    return True

def js(expr):
    r = send('Runtime.evaluate', {'expression': expr, 'returnByValue': True, 'awaitPromise': True})
    return (r.get('result') or {}).get('value')

goto('http://127.0.0.1:8767/', 5)
w('title:', js('document.title'))
w('tracks loaded:', js('S.tracks.length'))
w('#boot hidden:', js("document.getElementById('boot').style.display"))
w('view html len:', js("document.getElementById('view').innerHTML.length"))
shot(r'D:\air\qqbuddy\mountainriverechoes\daiplayer\_shot_home.png')

# 全部歌曲
js("navTo('all',null)"); time.sleep(2)
shot(r'D:\air\qqbuddy\mountainriverechoes\daiplayer\_shot_all.png')
w('rows:', js("document.querySelectorAll('.srow').length"))

# 歌手
js("navTo('singers',null)"); time.sleep(2)
shot(r'D:\air\qqbuddy\mountainriverechoes\daiplayer\_shot_singers.png')

# 歌手详情
js("navTo('artist','傣族电台')"); time.sleep(2.5)
shot(r'D:\air\qqbuddy\mountainriverechoes\daiplayer\_shot_artist.png')

# 点击第一首播放
js("document.querySelector('.srow').click()"); time.sleep(6)
w('cur:', js('P.cur'), 'queue:', js('P.queue.length'))
w('audio src:', js("(document.getElementById('audio').src||'').slice(0,90)"))
w('audio readyState:', js("document.getElementById('audio').readyState"), 'err:', js("document.getElementById('audio').error && document.getElementById('audio').error.code"))
shot(r'D:\air\qqbuddy\mountainriverechoes\daiplayer\_shot_playing.png')

# 歌词页
js("openPlayer()"); time.sleep(3)
w('lyric lines:', js("document.querySelectorAll('#plLyric p').length"))
shot(r'D:\air\qqbuddy\mountainriverechoes\daiplayer\_shot_lyric.png')
js("document.getElementById('player').classList.remove('open')")

# 专辑
js("navTo('albums',null)"); time.sleep(2)
shot(r'D:\air\qqbuddy\mountainriverechoes\daiplayer\_shot_albums.png')
js("navTo('album', S.albums[3].name)"); time.sleep(2.5)
shot(r'D:\air\qqbuddy\mountainriverechoes\daiplayer\_shot_album.png')

# 音源
js("navTo('sources',null)"); time.sleep(1.6)
shot(r'D:\air\qqbuddy\mountainriverechoes\daiplayer\_shot_sources.png')

# 搜索
js("document.getElementById('q').value='葫芦丝'; document.getElementById('q').dispatchEvent(new Event('input'))"); time.sleep(2.5)
shot(r'D:\air\qqbuddy\mountainriverechoes\daiplayer\_shot_search.png')

# 收藏
js("toggleFav(0); toggleFav(1); navTo('fav',null)"); time.sleep(2)
shot(r'D:\air\qqbuddy\mountainriverechoes\daiplayer\_shot_fav.png')

# 队列
js("document.getElementById('queue').classList.add('open')"); time.sleep(1.2)
shot(r'D:\air\qqbuddy\mountainriverechoes\daiplayer\_shot_queue.png')

# 音频流可解码性校验(直接喂代理流, 绕开 autoplay 限制)
js("(function(){var a=document.getElementById('audio');a.muted=true;a.src='/api/proxy?id='+P.cur;a.load();return 1})()")
time.sleep(6)
w('\nAUDIO readyState:', js("document.getElementById('audio').readyState"),
  '| duration:', js("document.getElementById('audio').duration"),
  '| err:', js("document.getElementById('audio').error && document.getElementById('audio').error.code"),
  '| src:', js("(document.getElementById('audio').src||'').slice(0,60)"))

w('\n--- console/log ---')
for l in logs[:60]:
    w(' ', l)
ws.close()
print('done')
