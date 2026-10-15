# -*- coding: utf-8 -*-
"""傣音廊 · 应用后端
====================
Flask 提供本地 API: 曲库索引下发 / 直链解析(含续签) / 音频代理 / 歌词 / 收藏与歌单。

跑法: `python app.py`(仅服务) 或 `python launcher.py`(服务 + 独立窗口)。
"""
import os
import io
import re
import json
import time
import gzip
import threading
from contextlib import suppress

import requests
from flask import Flask, jsonify, request, Response, send_from_directory, abort

from library import Library, State, app_dir
from reissue import Resolver, stats_text, UA

HERE = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(HERE, 'ui')
ASSETS_DIR = os.path.join(HERE, 'assets', 'ui')

app = Flask(__name__, static_folder=None)
app.config['JSON_AS_ASCII'] = False

LIB = Library()
STATE = State()
RESOLVER = Resolver(LIB, log=lambda s: print(s, flush=True))

START_TS = time.time()


def _gzip(html, status=200, ctype='application/json; charset=utf-8', extra=None):
    body = html.encode('utf-8') if isinstance(html, str) else html
    headers = dict(extra or {})
    if 'gzip' in (request.headers.get('Accept-Encoding') or '').lower() and len(body) > 1400:
        body = gzip.compress(body, 6)
        headers['Content-Encoding'] = 'gzip'
        headers['Vary'] = 'Accept-Encoding'
    headers.setdefault('Cache-Control', 'no-store')
    return Response(body, status=status, content_type=ctype, headers=headers)


# ------------------------------------------------------------------ 静态

@app.route('/')
def index():
    p = os.path.join(UI_DIR, 'index.html')
    with io.open(p, encoding='utf-8') as f:
        return _gzip(f.read(), ctype='text/html; charset=utf-8')


@app.route('/ui/<path:fn>')
def ui_file(fn):
    return send_from_directory(UI_DIR, fn)


@app.route('/assets/<path:fn>')
def asset_file(fn):
    return send_from_directory(ASSETS_DIR, fn)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(ASSETS_DIR, 'icon.png')


# ------------------------------------------------------------------ API

def _brief(i):
    r = LIB.idx[i]
    return dict(r)


@app.route('/api/bootstrap')
def api_bootstrap():
    hot = LIB.hot(24)
    return _gzip(json.dumps({
        'meta': LIB.meta,
        'tracks': LIB.idx,
        'singers': LIB.singers[:600],
        'albums': LIB.albums[:600],
        'sources': LIB.sources,
        'hot': hot,
        'state': STATE.data,
        'server': {'version': '1.2.2', 'uptime': round(time.time() - START_TS, 1)},
    }, ensure_ascii=False))


@app.route('/api/health')
def api_health():
    return jsonify({'ok': True, 'tracks': len(LIB.idx), 'path': str(LIB.path),
                    'stats': RESOLVER.stats, 'uptime': round(time.time() - START_TS, 1)})


@app.route('/api/url')
def api_url():
    try:
        i = int(request.args.get('id', '-1'))
    except ValueError:
        return jsonify({'ok': False, 'note': 'id 非法'}), 400
    force = request.args.get('force') in ('1', 'true')
    if i < 0 or i >= len(LIB.idx):
        return jsonify({'ok': False, 'note': '曲目不存在'}), 404
    res = RESOLVER.resolve(i, force=force)
    out = dict(res)
    out['viaCn'] = stats_text(res)
    out['stream'] = '/api/proxy?id=%d' % i
    return jsonify(out)


_PROXY_REF = (
    (('music.126.net', 'music.163.com'), 'https://music.163.com/'),
    (('kuwo.cn',), 'http://www.kuwo.cn/'),
    (('kugou.com',), 'https://www.kugou.com/'),
    (('migu.cn',), 'https://music.migu.cn/'),
    (('bilivideo.com', 'bilibili.com'), 'https://www.bilibili.com/'),
)


def _proxy_headers(url, rng=None):
    h = {'User-Agent': UA}
    for hosts, ref in _PROXY_REF:
        if any(x in url for x in hosts):
            h['Referer'] = ref
            break
    if rng:
        h['Range'] = rng
    return h


@app.route('/api/proxy')
def api_proxy():
    """音频代理: 浏览器直连失败(防盗链/CORS)时的兜底通道, 支持 Range 拖动进度。"""
    try:
        i = int(request.args.get('id', '-1'))
    except ValueError:
        abort(400)
    if i < 0 or i >= len(LIB.idx):
        abort(404)
    force = request.args.get('force') in ('1', 'true')
    res = RESOLVER.resolve(i, force=force)
    url = res.get('url') or ''
    if not url.startswith('http'):
        abort(502)
    rng = request.headers.get('Range')
    try:
        up = requests.get(url, headers=_proxy_headers(url, rng), stream=True,
                          timeout=(8, 30), allow_redirects=True)
    except Exception as e:
        return jsonify({'ok': False, 'note': '代理失败: %s' % e}), 502

    hop = ('content-type', 'content-length', 'content-range', 'accept-ranges', 'etag', 'last-modified')
    headers = {k: v for k, v in up.headers.items() if k.lower() in hop}
    headers.setdefault('Accept-Ranges', 'bytes')
    headers['Cache-Control'] = 'no-store'

    def gen():
        try:
            for chunk in up.iter_content(64 * 1024):
                if chunk:
                    yield chunk
        finally:
            up.close()

    return Response(gen(), status=up.status_code, headers=headers)


_IMG_REF = (
    (('hdslb.com', 'bilibili.com'), 'https://www.bilibili.com/'),
    (('qpic.cn', 'mp.weixin.qq.com', 'weixin.qq.com'), 'https://mp.weixin.qq.com/'),
    (('kuwo.cn',), 'http://www.kuwo.cn/'),
    (('music.126.net', 'music.163.com'), 'https://music.163.com/'),
    (('kugou.com',), 'https://www.kugou.com/'),
    (('migu.cn',), 'https://music.migu.cn/'),
)
_IMG_CACHE = {}


@app.route('/api/img')
def api_img():
    """封面代理: B站(i1.hdslb.com)与微信(mmbiz.qpic.cn)都有防盗链, 直连会 403 或返回"不可引用"占位图。"""
    u = request.args.get('u') or ''
    if not u.startswith('http'):
        abort(400)
    hit = _IMG_CACHE.get(u)
    if hit and time.time() - hit[0] < 6 * 3600:
        return Response(hit[1], content_type=hit[2],
                        headers={'Cache-Control': 'public, max-age=86400'})
    h = {'User-Agent': UA}
    for hosts, ref in _IMG_REF:
        if any(x in u for x in hosts):
            h['Referer'] = ref
            break
    try:
        r = requests.get(u, headers=h, timeout=(5, 12))
        if r.status_code != 200 or not r.content:
            abort(404)
        ct = r.headers.get('Content-Type') or 'image/jpeg'
        if len(_IMG_CACHE) > 900:
            _IMG_CACHE.clear()
        _IMG_CACHE[u] = (time.time(), r.content, ct)
        return Response(r.content, content_type=ct, headers={'Cache-Control': 'public, max-age=86400'})
    except Exception:
        abort(404)


@app.route('/api/lyric')
def api_lyric():
    try:
        i = int(request.args.get('id', '-1'))
    except ValueError:
        abort(400)
    lrc = LIB.lyric(i)
    src = '库内'
    if not lrc:
        # 网易云家族曲目可在线补歌词(identifier 即 songId)
        ident = LIB.song_identifier(i)
        if ident.isdigit():
            with suppress(Exception):
                r = requests.get('https://music.163.com/api/song/lyric',
                                 params={'id': ident, 'lv': 1, 'kv': 1, 'tv': -1},
                                 headers={'User-Agent': UA, 'Referer': 'https://music.163.com/'},
                                 timeout=6)
                d = r.json()
                lrc = ((d.get('lrc') or {}).get('lyric') or '')
                if lrc:
                    src = '网易云在线'
    return jsonify({'lrc': lrc or '', 'source': src if lrc else ''})


@app.route('/api/fav', methods=['POST'])
def api_fav():
    d = request.get_json(silent=True) or {}
    i = int(d.get('id', -1))
    if i < 0 or i >= len(LIB.idx):
        return jsonify({'ok': False}), 400
    fav = STATE.data['fav']
    if d.get('on'):
        if i not in fav:
            fav.append(i)
    else:
        STATE.data['fav'] = [x for x in fav if x != i]
    STATE.save()
    return jsonify({'ok': True, 'fav': STATE.data['fav']})


@app.route('/api/playlist', methods=['POST'])
def api_playlist():
    d = request.get_json(silent=True) or {}
    op = d.get('op')
    pls = STATE.data['playlists']
    if op == 'create':
        pid = 'pl%d' % int(time.time() * 1000)
        pls.insert(0, {'id': pid, 'name': (d.get('name') or '新建歌单').strip()[:24],
                       'cover': '', 'ids': [], 'created': time.time()})
        STATE.save()
        return jsonify({'ok': True, 'playlists': pls, 'id': pid})
    if op in ('rename', 'delete', 'add', 'remove'):
        pid = d.get('id')
        tgt = next((p for p in pls if p['id'] == pid), None)
        if not tgt:
            return jsonify({'ok': False, 'note': '歌单不存在'}), 404
        if op == 'rename':
            tgt['name'] = (d.get('name') or tgt['name']).strip()[:24]
        elif op == 'delete':
            pls.remove(tgt)
        elif op == 'add':
            for x in (d.get('ids') or [d.get('sid')]):
                x = int(x)
                if x not in tgt['ids']:
                    tgt['ids'].append(x)
                    if not tgt['cover']:
                        tgt['cover'] = LIB.idx[x]['c']
        elif op == 'remove':
            x = int(d.get('sid'))
            tgt['ids'] = [y for y in tgt['ids'] if y != x]
        STATE.save()
        return jsonify({'ok': True, 'playlists': pls})
    return jsonify({'ok': False, 'note': '未知操作'}), 400


@app.route('/api/recent', methods=['POST'])
def api_recent():
    d = request.get_json(silent=True) or {}
    with suppress(Exception):
        STATE.push_recent(int(d.get('id')))
    return jsonify({'ok': True, 'recent': STATE.data['recent']})


@app.route('/api/settings', methods=['POST'])
def api_settings():
    d = request.get_json(silent=True) or {}
    s = STATE.data['settings']
    for k in ('volume', 'mode', 'quality', 'skin'):
        if k in d:
            s[k] = d[k]
    STATE.save()
    return jsonify({'ok': True, 'settings': s})


@app.route('/api/search')
def api_search():
    return jsonify({'ids': LIB.search(request.args.get('q') or '', limit=int(request.args.get('n') or 80))})


def serve(host='127.0.0.1', port=8767):
    """启动服务(阻塞)。"""
    app.run(host=host, port=port, debug=False, threaded=True, use_reloader=False)


if __name__ == '__main__':
    port = int(os.environ.get('DAI_PORT') or 8767)
    print('[dai] library: %s (%d tracks, %.2fs)' % (LIB.path, len(LIB.idx), LIB.meta['load_seconds']))
    print('[dai] serving on http://127.0.0.1:%d' % port)
    serve(port=port)
