# -*- coding: utf-8 -*-
"""傣音廊 · 直链续签
====================
曲库里存的是各家音乐平台的**带签名直链**, 天然带时效(网易云约 40 分钟、酷我数天、酷狗更短),
所以播放前需要"验活 -> 失效则按 id 重签"。

按 `identifier` 精确续签, 不做模糊匹配 —— 同名不同曲顶替是这类库最典型的翻车点。
"""
import re
import time
import base64
import threading
from contextlib import suppress

import requests

from kuwocrypt import KuwoCrypt

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36')

# 永久/长效直链域名: 命中即视为无需续签
STABLE_HOSTS = ('res.wx.qq.com', 'mmbiz.qpic.cn')
# 网易云家族域名(网易云本体 / MyFreeMP3 / 音乐库 三家的直链都落在 126.net)
NETEASE_HOSTS = ('music.126.net', 'music.163.com')
KUWO_HOSTS = ('kuwo.cn',)
KUGOU_HOSTS = ('kugou.com',)
MIGU_HOSTS = ('migu.cn',)
BILI_HOSTS = ('bilivideo.com', 'bilibili.com', 'hdslb.com')

_STRIP = re.compile(r"[\s\-—－·・,，.。'\"‘’`~～!！?？:：;；()（）\[\]【】{}<>《》&^%$#@*+=|\\/]+")


def title_key(s):
    return _STRIP.sub('', str(s or '').lower())


def same_recording(a_name, a_singer, b_name, b_singer):
    """归一化歌名全等 + 歌手相容 —— 只有同一首歌才允许顶替直链。"""
    an, bn = title_key(a_name), title_key(b_name)
    if not an or not bn or an != bn:
        return False
    xa, xb = title_key(a_singer), title_key(b_singer)
    if not xa or not xb or xa == xb:
        return True
    return (len(xa) >= 2 and xa in xb) or (len(xb) >= 2 and xb in xa)


def host_of(url):
    m = re.match(r'https?://([^/?#]+)', str(url or ''))
    return m.group(1).lower() if m else ''


def has(url, hosts):
    h = host_of(url)
    return any(h.endswith(x) or h == x for x in hosts)


class Resolver:
    """带缓存的直链解析器。"""

    TTL_OK = 15 * 60          # 验活成功缓存 15 分钟
    TTL_FAIL = 60             # 失败缓存 1 分钟(避免反复打源站)
    PROBE_TIMEOUT = 6

    def __init__(self, lib, log=None):
        self.lib = lib
        self._cache = {}
        self._lock = threading.Lock()
        # API 调用用带 UA 的 session(搜索/续签接口需要 cookie 保持)
        self._sess = requests.Session()
        self._sess.headers.update({'User-Agent': UA})
        self.log = log or (lambda *a: None)
        self.stats = {'direct': 0, 'stable': 0, 'netease': 0, 'kuwo': 0,
                      'kugou': 0, 'migu': 0, 'bili': 0, 'search': 0, 'fail': 0}

    # ---------------------------------------------------------- 验活
    # 各源 CDN 对 Referer 挑剔: 少了它 Chrome UA 也 403; 带错源站的 Referer 同样被拒。
    _REFERER = (
        (NETEASE_HOSTS, 'https://music.163.com/'),
        (KUWO_HOSTS, 'http://www.kuwo.cn/'),
        (KUGOU_HOSTS, 'https://www.kugou.com/'),
        (MIGU_HOSTS, 'https://music.migu.cn/'),
        (BILI_HOSTS, 'https://www.bilibili.com/'),
    )

    def _headers_for(self, url):
        h = {'Range': 'bytes=0-1023', 'User-Agent': UA}
        for hosts, ref in self._REFERER:
            if has(url, hosts):
                h['Referer'] = ref
                break
        return h

    def probe(self, url):
        """验活。

        ⚠️ 必须用**不带 cookie 的裸请求**: 复用 session 时前面探测网易云留下的 cookie 会被
        酷我 CDN 视为异常请求直接 404(实测同一个新签直链, 裸请求 206 / 带 cookie session 404)。
        CSDN 类 CDN 校验的是 (UA + Referer + 无多余 cookie) 这个组合。
        """
        if not url or not str(url).startswith('http'):
            return False
        try:
            r = requests.get(url, headers=self._headers_for(url), stream=True,
                             timeout=self.PROBE_TIMEOUT, allow_redirects=True)
            ok = r.status_code in (200, 206)
            if ok:
                ctype = (r.headers.get('Content-Type') or '').lower()
                if 'text/html' in ctype:
                    ok = False
            r.close()
            return ok
        except Exception:
            return False

    # ---------------------------------------------------------- 主入口
    def resolve(self, i, force=False):
        now = time.time()
        with self._lock:
            c = self._cache.get(i)
        if c and not force:
            ttl = self.TTL_OK if c['ok'] else self.TTL_FAIL
            if now - c['ts'] < ttl:
                return dict(c, cached=True)

        t = self.lib.get(i)
        if not t:
            return {'ok': False, 'url': '', 'via': 'missing', 'note': '曲目不存在'}
        s = t.get('_song') or {}
        orig = str(s.get('download_url') or '').strip()
        ident = str(s.get('identifier') or '').strip()
        source = str(s.get('source') or '').strip()
        name = t.get('song_name') or s.get('song_name') or ''
        singer = t.get('singers') or s.get('singers') or ''

        res = None
        # ① 永久链直接放行(微信公众号音频)
        if orig and has(orig, STABLE_HOSTS) and '/voice/getvoice' in orig:
            res = {'ok': True, 'url': orig, 'via': 'stable', 'note': '微信公众号音频(永不过期)'}
        # ② 原链仍活着
        if res is None and self.probe(orig):
            res = {'ok': True, 'url': orig, 'via': 'direct', 'note': '原直链有效'}
        # ③ 按源续签(必须复验: 续签接口偶尔也返回已废链接)
        if res is None:
            cand = self._reissue(i, orig, ident, source, name, singer,
                                 str(t.get('album_url') or ''))
            if cand and self.probe(cand.get('url') or ''):
                res = cand
        # ④ 跨源精确同名重搜兜底
        if res is None:
            cand = self._search_fallback(name, singer, orig)
            if cand and self.probe(cand.get('url') or ''):
                res = cand

        if res is None:
            res = {'ok': False, 'url': orig, 'via': 'fail',
                   'note': '音源已失效, 且续签/同名重搜均未取到可用直链'}

        res['ts'] = now
        res['i'] = i
        key = res['via'] if res['via'] in self.stats else 'fail'
        with self._lock:
            self._cache[i] = res
            self.stats[key] = self.stats.get(key, 0) + 1
        if res.get('url') and res['via'] not in ('direct', 'stable'):
            self.log('[reissue] #%s %s - %s -> %s' % (i, name, res['via'], res.get('note')))
        return dict(res)

    # ---------------------------------------------------------- 各源续签
    def _reissue(self, i, orig, ident, source, name, singer, album_url=''):
        low = source.lower()
        # --- 网易云家族: 网易云 / MyFreeMP3 / 音乐库 (直链均落 126.net, identifier 为数字 songId)
        if ident.isdigit() and (has(orig, NETEASE_HOSTS) or 'netease' in low
                                or 'myfree' in low or 'yinyueku' in low):
            u = self._netease_by_id(ident)
            if u:
                return {'ok': True, 'url': u, 'via': 'netease', 'note': '网易云按 id 重签'}
        # --- 酷我: identifier 为 rid
        if ident.isdigit() and (has(orig, KUWO_HOSTS) or 'kuwo' in low):
            u = self._kuwo_by_rid(ident)
            if u:
                return {'ok': True, 'url': u, 'via': 'kuwo', 'note': '酷我按 rid 重签'}
        # --- 酷狗: identifier 为 hash(16位hex)
        if re.fullmatch(r'[0-9A-Fa-f]{16,40}', ident) and (has(orig, KUGOU_HOSTS) or 'kugou' in low):
            u = self._kugou_by_hash(ident)
            if u:
                return {'ok': True, 'url': u, 'via': 'kugou', 'note': '酷狗按 hash 重签'}
        # --- 咪咕
        if ident.isdigit() and (has(orig, MIGU_HOSTS) or 'migu' in low):
            u = self._migu_by_id(ident, name, singer)
            if u:
                return {'ok': True, 'url': u, 'via': 'migu', 'note': '咪咕重签'}
        # --- B站: upos 直链带签名时效, 但 album_url 里存了 BV 号, 可回官方接口重取
        if has(orig, BILI_HOSTS) or 'bili' in low:
            m = re.search(r'(BV[0-9A-Za-z]{10})', str(album_url or ''))
            if m:
                u = self._bili_by_bvid(m.group(1))
                if u:
                    return {'ok': True, 'url': u, 'via': 'bili',
                            'note': 'B站回源重解析(%s)' % m.group(1)}
        return None

    # -- 网易云 -----------------------------------------------------
    def _netease_by_id(self, song_id):
        with suppress(Exception):
            r = self._sess.get('https://music.163.com/api/song/enhance/player/url',
                               params={'ids': '[%s]' % song_id, 'br': 320000},
                               headers={'Referer': 'https://music.163.com/'}, timeout=8)
            d = (r.json().get('data') or [{}])[0]
            if d.get('url'):
                return d['url']
        # 换 v1 接口再试一次(部分曲目只有 v1 有)
        with suppress(Exception):
            r = self._sess.get('https://interface3.music.163.com/api/song/enhance/player/url',
                               params={'ids': '[%s]' % song_id, 'br': 320000},
                               headers={'Referer': 'https://music.163.com/'}, timeout=8)
            d = (r.json().get('data') or [{}])[0]
            if d.get('url'):
                return d['url']
        return None

    def _netease_search(self, kw, limit=8):
        """网易云搜索(无需登录): 返回 [{id,name,singers,album,duration}]"""
        out = []
        with suppress(Exception):
            r = self._sess.post('https://music.163.com/api/search/get/web',
                                data={'s': kw, 'type': 1, 'offset': 0, 'limit': limit, 'total': 'true'},
                                headers={'Referer': 'https://music.163.com/'}, timeout=8)
            for s in ((r.json().get('result') or {}).get('songs') or []):
                out.append({
                    'id': str(s.get('id')),
                    'name': s.get('name') or '',
                    'singers': ','.join(a.get('name') or '' for a in (s.get('artists') or [])),
                    'album': ((s.get('album') or {}).get('name') or ''),
                    'duration': int((s.get('duration') or 0) / 1000),
                })
        return out

    # -- 酷我 -------------------------------------------------------
    def _kuwo_by_rid(self, rid):
        try:
            q = ('user=0&corp=kuwo&source=kwplayer_ar_5.1.0.0_B_jiakong_vh.apk&p2p=1'
                 '&type=convert_url2&sig=0&format=mp3&rid=%s' % rid)
            enc = KuwoCrypt.encryptquery(q)
            url = 'http://mobi.kuwo.cn/mobi.s?f=kuwo&q=' + enc
            r = self._sess.get(url, headers={'user-agent': 'okhttp/3.10.0'}, timeout=8)
            m = re.search(r'http[^\s$\"]+', r.text or '')
            if m:
                u = m.group(0).strip()
                if u.startswith('http'):
                    return u
        except Exception:
            pass
        # 备选: 官方 playUrl
        with suppress(Exception):
            r = self._sess.get('https://www.kuwo.cn/api/v1/www/music/playUrl',
                               params={'mid': rid, 'type': 'music', 'httpsStatus': 1},
                               headers={'Referer': 'https://www.kuwo.cn/', 'csrf': 'x'}, timeout=8)
            u = ((r.json().get('data') or {}).get('url') or '')
            if u.startswith('http'):
                return u
        return None

    # -- 酷狗 -------------------------------------------------------
    def _kugou_by_hash(self, h):
        with suppress(Exception):
            self._sess.get('https://www.kugou.com/', timeout=6)   # 取 kg_mid cookie
        params = {
            'r': 'play/getdata', 'hash': h, 'album_id': '', 'dfid': '-',
            'appid': '1014', 'mid': '1', 'platid': '4',
            'encode_albums': '1', 'encode_album_audio_id': '',
        }
        with suppress(Exception):
            r = self._sess.get('https://wwwapi.kugou.com/yy/index.php', params=params,
                               headers={'Referer': 'https://www.kugou.com/'}, timeout=8)
            d = r.json().get('data') or {}
            # 有的曲目 主链 空, 备用链在 play_backup_url
            u = (d.get('play_url') or d.get('play_backup_url') or '').strip()
            if u.startswith('http'):
                return u.replace('\\/', '/')
        return None

    # -- 咪咕 -------------------------------------------------------
    def _migu_by_id(self, cid, name, singer):
        with suppress(Exception):
            r = self._sess.get('https://app.c.nf.migu.cn/MIGUM2.0/v1.0/content/sub/listenSong.do',
                               params={'toneFlag': 'HQ', 'netType': '00',
                                       'userId': '15548614588710179085069', 'ua': 'Android_migu',
                                       'version': '5.0.1', 'copyrightId': cid, 'contentId': cid,
                                       'resourceType': '2', 'channel': '0'},
                               timeout=8)
            u = ((r.json().get('data') or {}).get('url') or '')
            if u.startswith('http'):
                return u
        return None

    # -- B站 --------------------------------------------------------
    def _bili_by_bvid(self, bvid):
        """BV 号 -> 视频音频流直链。

        B 站 upos 链时效短, 但曲库每条 B 站曲目的 album_url 里留着 BV 号, 可以走
        `view`(取 aid/cid) + `player/playurl`(dash.audio) 重新签一份 —— 等效永不过期。
        """
        aid = cid = None
        with suppress(Exception):
            r = self._sess.get('https://api.bilibili.com/x/web-interface/view',
                               params={'bvid': bvid},
                               headers={'Referer': 'https://www.bilibili.com/'}, timeout=8)
            d = r.json().get('data') or {}
            aid, cid = d.get('aid'), d.get('cid')
        if not aid or not cid:
            return None
        with suppress(Exception):
            r = self._sess.get('https://api.bilibili.com/x/player/playurl',
                               params={'avid': aid, 'cid': cid, 'qn': 64, 'fnval': 16, 'fourk': 1},
                               headers={'Referer': 'https://www.bilibili.com/video/%s' % bvid},
                               timeout=8)
            dash = (r.json().get('data') or {}).get('dash') or {}
            for a in (dash.get('audio') or []):
                u = (a.get('baseUrl') or '').strip()
                if not u:
                    bu = a.get('backupUrl') or []
                    u = (bu[0] if bu else '').strip()
                if u.startswith('http'):
                    return u
        return None

    # -- 跨源兜底 ---------------------------------------------------
    def _search_fallback(self, name, singer, orig):
        """网易云精确同名同歌手重搜 -> 按新 id 取链。判据严(见 same_recording), 宁缺勿错。"""
        if not name:
            return None
        short = re.split(r'[（(\[【]', name)[0].strip() or name
        for kw in (('%s %s' % (short, singer)).strip(), short):
            for hit in self._netease_search(kw):
                if not same_recording(name, singer, hit['name'], hit['singers']):
                    continue
                u = self._netease_by_id(hit['id'])
                if u:
                    return {'ok': True, 'url': u, 'via': 'search',
                            'note': '网易云同名重搜命中(id=%s)' % hit['id']}
        return None


def stats_text(res):
    m = {'direct': '原链', 'stable': '永久链', 'netease': '网易云续签', 'kuwo': '酷我续签',
         'kugou': '酷狗续签', 'migu': '咪咕续签', 'bili': 'B站重解析',
         'search': '同名重搜', 'fail': '失败'}
    return m.get(res.get('via'), res.get('via') or '?')
