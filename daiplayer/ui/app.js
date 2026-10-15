/* ============================================================
   傣音廊 · 前端
   ============================================================ */
const $ = s => document.querySelector(s);
const $$ = s => Array.prototype.slice.call(document.querySelectorAll(s));
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
const fmtTime = s => { s = Math.max(0, Math.floor(s || 0)); const m = Math.floor(s / 60); return `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`; };
const fmtNum = n => n >= 10000 ? (n / 10000).toFixed(1) + '万' : String(n);

const COVERS = ['cv_peacock.png', 'cv_hulusi.png', 'cv_drum.png', 'cv_water.png', 'cv_brocade.png', 'cv_bamboo.png'];
const localCover = i => '/assets/' + COVERS[(i || 0) % COVERS.length];
/* B站/微信封面有防盗链, 直连会 403 或显示"不可引用"占位图 -> 走本地代理 */
const NEED_PROXY = /hdslb\.com|qpic\.cn|weixin\.qq\.com/i;
const imgURL = u => (u && NEED_PROXY.test(u)) ? ('/api/img?u=' + encodeURIComponent(u)) : u;
const coverOf = r => {
  if (!r) return localCover(0);
  const c = imgURL(r.c);
  return c || localCover(r.i);
};

/* ---------------- 换肤 ---------------- */
const SKINS = [
  { id: 'peacock',  name: '孔雀绿', c: '#0E6E63' },
  { id: 'gold',     name: '金傣',   c: '#B8761E' },
  { id: 'cinnabar', name: '朱砂红', c: '#B23A2E' },
  { id: 'night',    name: '夜澜',   c: '#1FB8A6' },
  { id: 'betel',    name: '贝叶',   c: '#0F7A6E' },
  { id: 'brocade',  name: '织锦',   c: '#0E7C6B' },
];
function applySkin(id) {
  if (!SKINS.some(s => s.id === id)) id = 'peacock';
  document.documentElement.setAttribute('data-skin', id);
  try { localStorage.setItem('dai_skin', id); } catch (e) {}
  $$('#skinPop .swatch').forEach(el => el.classList.toggle('on', el.dataset.skin === id));
}
/* 皮肤选择器 */
const skinPop = $('#skinPop');
skinPop.innerHTML = '<div class="skin-pop-h">播放界面皮肤</div>' + SKINS.map(s =>
  `<button class="swatch" data-skin="${s.id}" title="${s.name}" style="--sw:${s.c}"><i></i><span>${s.name}</span></button>`).join('');
skinPop.querySelectorAll('.swatch').forEach(b => b.onclick = () => {
  applySkin(b.dataset.skin);
  api('/api/settings', { skin: b.dataset.skin });
  toast('已切换至「' + b.title + '」皮肤');
  setTimeout(() => skinPop.classList.remove('open'), 220);
});
$('#btnSkin').onclick = e => { e.stopPropagation(); skinPop.classList.toggle('open'); };
document.addEventListener('click', e => {
  if (!e.target.closest('#skinPop') && !e.target.closest('#btnSkin')) skinPop.classList.remove('open');
});
/* 先用本地记忆的皮肤渲染, 避免闪一下默认主题 */
try { const _ls = localStorage.getItem('dai_skin'); if (_ls) applySkin(_ls); } catch (e) { }

const S = { tracks: [], singers: [], albums: [], sources: [], hot: [], meta: {}, fav: new Set(), playlists: [], recent: [] };
const P = { queue: [], qi: -1, mode: 'list', vol: 0.8, cur: -1, srcMode: '', ctx: { view: 'all' }, shuffled: [] };
const H = { stack: [], pos: -1 };
const audio = $('#audio');
let ctxMenuId = -1;

/* ---------------- 图片兜底 ---------------- */
document.addEventListener('error', e => {
  const t = e.target;
  if (t && t.tagName === 'IMG' && !t.dataset.fb) {
    t.dataset.fb = '1';
    t.src = localCover(parseInt(t.dataset.i || '0', 10));
  }
}, true);

/* ---------------- 启动 ---------------- */
(async function boot() {
  try {
    const tip = $('#bootTip');
    const steps = ['正在唤醒傣族曲库…', '解析傣族曲库…', '聚合作曲家与专辑…', '准备完毕'];
    let k = 0;
    const timer = setInterval(() => { if (k < steps.length) tip.textContent = steps[k++]; }, 420);

    const res = await fetch('/api/bootstrap');
    const d = await res.json();
    clearInterval(timer);

    S.meta = d.meta; S.tracks = d.tracks; S.singers = d.singers;
    S.albums = d.albums; S.sources = d.sources; S.hot = d.hot;
    S.fav = new Set(d.state.fav || []);
    S.playlists = d.state.playlists || [];
    S.recent = d.state.recent || [];
    P.vol = (d.state.settings || {}).volume ?? 0.8;
    P.mode = (d.state.settings || {}).mode || 'list';
    applySkin((d.state.settings || {}).skin || 'peacock');

    $('#vol').value = Math.round(P.vol * 100);
    audio.volume = P.vol;
    $('#libInfo').innerHTML = `${esc(S.meta.group)} · ${S.tracks.length} 首<br>${esc(String(S.meta.data_file || '').split('\\').pop())}`;
    $('#chipStat').innerHTML = `曲库 <b>${fmtNum(S.tracks.length)}</b> 首 · 歌手 <b>${fmtNum(S.singers.length)}</b> 位`;

    $('#boot').style.display = 'none';
    $('#app').hidden = false;
    $('#playbar').hidden = false;
    document.title = `${S.meta.name} · 傣音廊`;
    renderPlaylists();
    navTo('home', null, true);
    syncPlayUI();
  } catch (err) {
    $('#bootTip').textContent = '加载失败: ' + err.message;
  }
})();

/* ---------------- 视图路由 ---------------- */
function navTo(view, param, replace) {
  const key = view + '|' + (param ?? '');
  if (!replace && H.stack[H.pos] === key) return;
  if (!replace) { H.stack = H.stack.slice(0, H.pos + 1); H.stack.push(key); H.pos = H.stack.length - 1; }
  else if (H.pos < 0) { H.stack.push(key); H.pos = 0; }
  $$('#navMain a, #navMine a').forEach(a => a.classList.toggle('on', a.dataset.view === view));
  $$('#plList a').forEach(a => a.classList.toggle('on', view === 'playlist' && a.dataset.pid === param));
  const v = $('#view');
  v.scrollTop = 0;
  ({ home: renderHome, all: renderAll, singers: renderSingers, albums: renderAlbums,
     sources: renderSources, fav: renderFav, recent: renderRecent,
     artist: renderArtist, album: renderAlbum, playlist: renderPlaylist, search: renderSearch }[view]
    || renderHome)(param, v);
}
$('#btnBack').onclick = () => { if (H.pos > 0) { H.pos--; replay(H.stack[H.pos]); } };
$('#btnFwd').onclick = () => { if (H.pos < H.stack.length - 1) { H.pos++; replay(H.stack[H.pos]); } };
function replay(key) { const [v, p] = key.split('|'); $$('#navMain a, #navMine a').forEach(a => a.classList.toggle('on', a.dataset.view === v)); renderByKey(v, p); }
function renderByKey(v, p) {
  const vw = $('#view'); vw.scrollTop = 0;
  ({ home: renderHome, all: renderAll, singers: renderSingers, albums: renderAlbums, sources: renderSources,
     fav: renderFav, recent: renderRecent, artist: renderArtist, album: renderAlbum, playlist: renderPlaylist, search: renderSearch }[v] || renderHome)(p, vw);
}
$('#navMain').onclick = $('#navMine').onclick = e => { const a = e.target.closest('a[data-view]'); if (a) navTo(a.dataset.view, null); };

/* ---------------- 首页 ---------------- */
function renderHome(_p, v) {
  const hot = S.hot.slice(0, 12);
  const albums = S.albums.slice(0, 12);
  const newish = S.singers.filter(s => !/电台|合唱|经典傣歌|未知|网络歌手/.test(s.name)).slice(0, 12);
  v.innerHTML = `
  <div class="banner">
    <img src="/assets/banner.jpg" alt="">
    <div class="b-in">
      <h1>傣音廊 · 云岭傣乡的歌声</h1>
      <p>从西双版纳到德宏，从瑞丽江到孟连耿马 —— 章哈、葫芦丝、象脚鼓与傣语情歌，${fmtNum(S.tracks.length)} 首傣族音乐已就绪，共 ${fmtNum(S.singers.length)} 位歌手、${fmtNum(S.albums.length)} 张专辑。</p>
      <div class="b-btns">
        <button class="btn pri" id="bPlay"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>随机播放</button>
        <button class="btn gho" id="bAll">进入曲库</button>
      </div>
    </div>
  </div>

  <div class="quick">
    <div class="qcard q1" data-go="all"><b>全部歌曲</b><span>${fmtNum(S.tracks.length)} 首傣族音乐</span><svg viewBox="0 0 24 24"><path d="M4 5h16v2H4zm0 6h16v2H4zm0 6h10v2H4z"/></svg></div>
    <div class="qcard q2" data-go="singers"><b>傣族歌手</b><span>${fmtNum(S.singers.length)} 位献声者</span><svg viewBox="0 0 24 24"><path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8m0 2c-4 0-8 2-8 4.5V21h16v-2.5C20 16 16 14 12 14"/></svg></div>
    <div class="qcard q3" data-go="albums"><b>专辑唱片</b><span>${fmtNum(S.albums.length)} 张专辑</span><svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20m0 13a3 3 0 1 1 0-6 3 3 0 0 1 0 6"/></svg></div>
    <div class="qcard q4" data-go="fav"><b>我喜欢的</b><span>${S.fav.size} 首收藏</span><svg viewBox="0 0 24 24"><path d="M12 21s-8-5.1-8-10.4A4.6 4.6 0 0 1 12 7a4.6 4.6 0 0 1 8 3.6C20 15.9 12 21 12 21"/></svg></div>
  </div>

  <section class="sec"><div class="sec-h"><h2>热门歌手</h2><span class="more" data-go="singers">查看全部 ›</span></div>
    <div class="grid">${newish.map(singerCard).join('')}</div></section>

  <section class="sec"><div class="sec-h"><h2>为你精选</h2><span class="more" data-go="all">更多 ›</span></div>
    ${songListHTML(hot, { compact: true })}</section>

  <section class="sec"><div class="sec-h"><h2>专辑唱片</h2><span class="more" data-go="albums">查看全部 ›</span></div>
    <div class="grid">${albums.map(albumCard).join('')}</div></section>`;

  v.querySelectorAll('[data-go]').forEach(n => n.onclick = () => navTo(n.dataset.go, null));
  $('#bPlay').onclick = () => { setQueue(S.hot.length ? S.hot : S.tracks.slice(0, 60).map(t => t.i), 0, { view: 'home' }); playAt(0); };
  $('#bAll').onclick = () => navTo('all', null);
  bindSongRows(v); bindCards(v);
}

function singerCard(s) {
  return `<div class="card round" data-singer="${esc(s.name)}">
    <div class="cv"><img loading="lazy" src="${esc(imgURL(s.cover) || localCover(s.name.length))}" data-i="${s.name.length % 4}" alt="">
      <span class="plays">${fmtNum(s.count)} 首</span></div>
    <div class="t">${esc(s.name)}</div><div class="s">傣族音乐人</div></div>`;
}
function albumCard(a) {
  return `<div class="card" data-album="${esc(a.name)}">
    <div class="cv"><img loading="lazy" src="${esc(imgURL(a.cover) || localCover(a.name.length))}" data-i="${a.name.length % 4}" alt="">
      <span class="plays">${fmtNum(a.count)} 首</span>
      <button class="pbtn" data-playalbum="${esc(a.name)}"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></button></div>
    <div class="t">${esc(a.name)}</div><div class="s">${esc(a.singer || '合辑')}</div></div>`;
}
function bindCards(v) {
  v.querySelectorAll('.card').forEach(c => {
    c.onclick = e => {
      const pb = e.target.closest('[data-playalbum]');
      if (pb) { e.stopPropagation(); const ids = idsByAlbum(pb.dataset.playalbum); if (ids.length) { setQueue(ids, 0, { view: 'album', name: pb.dataset.playalbum }); playAt(0); } return; }
      if (c.dataset.singer) navTo('artist', c.dataset.singer);
      else if (c.dataset.album) navTo('album', c.dataset.album);
      else if (c.dataset.pl) navTo('playlist', c.dataset.pl);
    };
  });
  v.querySelectorAll('.more[data-go]').forEach(n => n.onclick = () => navTo(n.dataset.go, null));
}

/* ---------------- 歌曲列表 ---------------- */
let LIST_LIMIT = 120;
function songRow(r, idx, ctxKey) {
  const liked = S.fav.has(r.i);
  return `<div class="srow" data-i="${r.i}" data-ix="${idx}">
    <div class="ix"><span class="num">${idx + 1}</span><span class="go"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></span></div>
    <div class="tcell"><img loading="lazy" src="${esc(coverOf(r))}" data-i="${r.i}" alt="">
      <div class="dd"><div class="nm" title="${esc(r.n)}">${esc(r.n)}${r.l ? '<span class="tag">词</span>' : ''}</div></div></div>
    <div class="ar">${esc(r.s)}</div>
    <div class="al">${albumCell(r)}</div>
    <div class="src">${esc(r.o)}</div>
    <div class="ops">
      <button data-act="like" class="${liked ? 'on' : ''}" title="喜欢"><svg viewBox="0 0 24 24"><path d="M12 21s-8-5.1-8-10.4A4.6 4.6 0 0 1 12 7a4.6 4.6 0 0 1 8 3.6C20 15.9 12 21 12 21"/></svg></button>
      <button data-act="more" title="更多"><svg viewBox="0 0 24 24"><path d="M6 10a2 2 0 1 0 0 4 2 2 0 0 0 0-4m6 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4m6 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4"/></svg></button>
    </div>
    <div class="du">${r.d ? fmtTime(r.d) : '--:--'}</div>
  </div>`;
}
/* B站条目把 BV 号存进了 album 字段, 当专辑名显示没有意义 */
function albumCell(r) {
  if (!r.a) return '—';
  if (/^BV[0-9A-Za-z]{10}$/.test(r.a)) return '<span style="color:#9AA2AE">B站视频</span>';
  return `<a data-album="${esc(r.a)}">${esc(r.a)}</a>`;
}
function songListHTML(ids, opt) {
  opt = opt || {};
  if (!ids.length) return `<div class="empty"><svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20m1 15h-2v-6h2zm0-8h-2V7h2z"/></svg><p>这里还没有歌曲</p><small>去曲库里挑几首吧</small></div>`;
  const n = Math.min(ids.length, opt.limit || LIST_LIMIT);
  const head = opt.compact ? '' : `<div class="shead"><span style="text-align:center">#</span><span>标题</span><span>歌手</span><span>专辑</span><span>音源</span><span></span><span style="text-align:right">时长</span></div>`;
  return `<div class="slist" data-ctx="${esc(opt.ctx || '')}">${head}${ids.slice(0, n).map((i, k) => songRow(S.tracks[i], k, opt.ctx)).join('')}</div>
    ${ids.length > n ? `<div class="more-row"><button class="btn" data-more="${n}">加载更多（还有 ${ids.length - n} 首）</button></div>` : ''}`;
}
function bindSongRows(root, ids) {
  root.querySelectorAll('[data-more]').forEach(b => b.onclick = () => {
    LIST_LIMIT += 200; renderByKey(...(H.stack[H.pos] || 'all|').split('|'));
  });
  root.querySelectorAll('.srow').forEach(row => {
    const i = +row.dataset.i;
    row.onclick = e => {
      const act = e.target.closest('[data-act]');
      const al = e.target.closest('[data-album]');
      if (al) { e.stopPropagation(); navTo('album', al.dataset.album); return; }
      if (act) {
        e.stopPropagation();
        if (act.dataset.act === 'like') toggleFav(i);
        else openCtx(e, i);
        return;
      }
      // 以当前列表为播发上下文
      const listEl = row.closest('.slist');
      let ids2 = listEl && listEl._ids ? listEl._ids : null;
      if (!ids2) ids2 = (P.ctx.ids && P.ctx.ids.includes(i)) ? P.ctx.ids : [i];
      const at = ids2.indexOf(i);
      setQueue(ids2, at < 0 ? 0 : at, P.ctx);
      playAt(at < 0 ? 0 : at);
    };
    row.oncontextmenu = e => { e.preventDefault(); openCtx(e, i); };
  });
  root.querySelectorAll('.slist').forEach(sl => {
    sl._ids = [...sl.querySelectorAll('.srow')].map(r => +r.dataset.i);
  });
}

/* ---------------- 各视图 ---------------- */
function renderAll() {
  const v = $('#view');
  v.innerHTML = `<section class="sec"><div class="sec-h"><h2>全部歌曲</h2><span class="more">共 ${fmtNum(S.tracks.length)} 首</span></div>
    <div class="slist-head"><button class="big-play" id="playAll"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></button>
      <div class="info">播放全部 · <b>${fmtNum(S.tracks.length)}</b> 首 · 来自 <b>${S.sources.length}</b> 个音源</div></div>
    ${songListHTML(S.tracks.map(t => t.i), { ctx: 'all' })}</section>`;
  const ids = S.tracks.map(t => t.i);
  $('#playAll').onclick = () => { setQueue(ids, 0, { view: 'all' }); playAt(0); };
  bindSongRows(v);
}

function renderSingers() {
  const v = $('#view');
  const list = S.singers;
  v.innerHTML = `<section class="sec"><div class="sec-h"><h2>傣族歌手</h2><span class="more">共 ${fmtNum(list.length)} 位</span></div>
    <div class="grid">${list.slice(0, LIST_LIMIT).map(singerCard).join('')}</div>
    ${list.length > LIST_LIMIT ? `<div class="more-row"><button class="btn" data-more="1">加载更多（还有 ${list.length - LIST_LIMIT} 位）</button></div>` : ''}</section>`;
  bindCards(v); bindMore(v, renderSingers);
}
function renderAlbums() {
  const v = $('#view');
  const list = S.albums;
  v.innerHTML = `<section class="sec"><div class="sec-h"><h2>专辑唱片</h2><span class="more">共 ${fmtNum(list.length)} 张</span></div>
    <div class="grid">${list.slice(0, LIST_LIMIT).map(albumCard).join('')}</div>
    ${list.length > LIST_LIMIT ? `<div class="more-row"><button class="btn" data-more="1">加载更多（还有 ${list.length - LIST_LIMIT} 张）</button></div>` : ''}</section>`;
  bindCards(v); bindMore(v, renderAlbums);
}
function renderSources() {
  const v = $('#view');
  const total = S.tracks.length;
  v.innerHTML = `<section class="sec"><div class="sec-h"><h2>音源分布</h2><span class="more">${S.sources.length} 个来源</span></div>
    <div class="grid">${S.sources.map((s, k) => `
      <div class="card" data-src="${esc(s.name)}">
        <div class="cv" style="display:grid;place-items:center;background:linear-gradient(135deg,${['#0E6E63,#12A594', '#B8761E,#D9A441', '#9E3522,#C8452F', '#0A544C,#0E6E63', '#2C5F8A,#4E8FBF'][k % 5]})">
          <div style="color:#fff;text-align:center">
            <div style="font-size:26px;font-weight:700;letter-spacing:.02em">${fmtNum(s.count)}</div>
            <div style="font-size:11px;opacity:.85">首 · ${(s.count * 100 / total).toFixed(1)}%</div>
          </div>
          <button class="pbtn" data-playsrc="${esc(s.name)}"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></button>
        </div>
        <div class="t">${esc(s.name)}</div><div class="s">点击查看全部</div></div>`).join('')}</div></section>`;
  v.querySelectorAll('.card').forEach(c => {
    c.onclick = e => {
      const pb = e.target.closest('[data-playsrc]');
      const name = c.dataset.src;
      if (pb) { e.stopPropagation(); const ids = idsBySource(name); if (ids.length) { setQueue(ids, 0, { view: 'source', name }); playAt(0); } return; }
      navTo('search', '\u0000src:' + name);
    };
  });
  bindMore(v, renderSources);
}
function renderFav() {
  const v = $('#view');
  const ids = [...S.fav].sort((a, b) => a - b);
  v.innerHTML = `<section class="sec"><div class="sec-h"><h2>我喜欢的音乐</h2><span class="more">${ids.length} 首</span></div>
    ${ids.length ? `<div class="slist-head"><button class="big-play" id="playFav"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></button><div class="info">播放全部</div></div>` : ''}
    ${songListHTML(ids, { ctx: 'fav' })}</section>`;
  const b = $('#playFav'); if (b) b.onclick = () => { setQueue(ids, 0, { view: 'fav' }); playAt(0); };
  bindSongRows(v);
}
function renderRecent() {
  const v = $('#view');
  const ids = S.recent.filter(i => S.tracks[i]);
  v.innerHTML = `<section class="sec"><div class="sec-h"><h2>最近播放</h2><span class="more">${ids.length} 首</span></div>
    ${songListHTML(ids, { ctx: 'recent' })}</section>`;
  bindSongRows(v);
}
function renderArtist(name) {
  const v = $('#view');
  const ids = idsBySinger(name);
  const s = S.singers.find(x => x.name === name) || { name, count: ids.length, cover: '' };
  if (LIST_LIMIT < 120) LIST_LIMIT = 120;
  v.innerHTML = `
    <div class="crumb"><a data-go="singers">歌手</a><svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg><span>${esc(name)}</span></div>
    <div class="artist-hero"><img src="${esc(imgURL(s.cover) || localCover(name.length))}" data-i="${name.length % 4}" alt="">
      <div class="ah"><div class="av"><img src="${esc(imgURL(s.cover) || localCover(name.length))}" data-i="${name.length % 4}" alt=""></div>
      <div class="an"><div class="k">DAI  MUSICIAN</div><h1>${esc(name)}</h1><p>库内收录 ${fmtNum(ids.length)} 首作品</p></div></div></div>
    <section class="sec"><div class="sec-h"><h2>热门作品</h2></div>
      <div class="slist-head"><button class="big-play" id="playAr"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></button><div class="info">播放全部 · <b>${ids.length}</b> 首</div></div>
      ${songListHTML(ids, { ctx: 'artist', ctxName: name })}</section>`;
  $('#playAr').onclick = () => { setQueue(ids, 0, { view: 'artist', name }); playAt(0); };
  v.querySelector('[data-go]').onclick = () => navTo('singers', null);
  bindSongRows(v);
}
function renderAlbum(name) {
  const v = $('#view');
  const ids = idsByAlbum(name);
  const a = S.albums.find(x => x.name === name) || { name, count: ids.length, cover: '', singer: '' };
  v.innerHTML = `
    <div class="crumb"><a data-go="albums">专辑</a><svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg><span>${esc(name)}</span></div>
    <div class="detail"><div class="dc"><img src="${esc(imgURL(a.cover) || localCover(name.length))}" data-i="${name.length % 4}" alt=""></div>
      <div class="di"><span class="k">专辑 / ALBUM</span><h1>${esc(name)}</h1>
        <div class="sub">歌手：<b>${esc(a.singer || '合辑')}</b><br>收录 <b>${ids.length}</b> 首</div>
        <div class="b-btns"><button class="btn pri" id="playAl"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>播放全部</button></div></div></div>
    <section class="sec">${songListHTML(ids, { ctx: 'album', ctxName: name })}</section>`;
  $('#playAl').onclick = () => { setQueue(ids, 0, { view: 'album', name }); playAt(0); };
  v.querySelector('[data-go]').onclick = () => navTo('albums', null);
  bindSongRows(v);
}
function renderPlaylist(pid) {
  const v = $('#view');
  const pl = S.playlists.find(p => p.id === pid);
  if (!pl) { renderFav(); return; }
  const ids = pl.ids.filter(i => S.tracks[i]);
  v.innerHTML = `
    <div class="crumb"><a>我的歌单</a><svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg><span>${esc(pl.name)}</span></div>
    <div class="detail"><div class="dc"><img src="${idsp(pl.cover) || localCover(ids.length)}" data-i="${ids.length % 4}" alt=""></div>
      <div class="di"><span class="k">歌单 / PLAYLIST</span><h1>${esc(pl.name)}</h1>
        <div class="sub">共 <b>${ids.length}</b> 首</div>
        <div class="b-btns"><button class="btn pri" id="playPl"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>播放全部</button>
          <button class="btn" id="renamePl">重命名</button><button class="btn" id="delPl">删除歌单</button></div></div></div>
    <section class="sec">${songListHTML(ids, { ctx: 'playlist', ctxName: pid })}</section>`;
  if (ids.length) $('#playPl').onclick = () => { setQueue(ids, 0, { view: 'playlist', pid, name: pl.name }); playAt(0); };
  $('#renamePl').onclick = () => askName('重命名歌单', pl.name, n => { api('/api/playlist', { op: 'rename', id: pid, name: n }).then(r => { if (r.ok) { S.playlists = r.playlists; renderPlaylists(); renderPlaylist(pid); } }); });
  $('#delPl').onclick = () => confirmBox('删除歌单', `确定删除《${pl.name}》吗？`, () => api('/api/playlist', { op: 'delete', id: pid }).then(r => { if (r.ok) { S.playlists = r.playlists; renderPlaylists(); navTo('home', null); } }));
  bindSongRows(v);
}
function idsp(c) { return imgURL(c) || ''; }

function renderSearch(q) {
  const v = $('#view');
  if (q.startsWith('\u0000src:')) {
    const name = q.slice(5);
    const ids = idsBySource(name);
    v.innerHTML = `<div class="crumb"><a data-go="sources">音源</a><svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg><span>${esc(name)}</span></div>
      <section class="sec"><div class="sec-h"><h2>${esc(name)} · 音源曲目</h2><span class="more">${fmtNum(ids.length)} 首</span></div>
      <div class="slist-head"><button class="big-play" id="playSrc"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></button><div class="info">播放全部</div></div>
      ${songListHTML(ids, { ctx: 'source', ctxName: name })}</section>`;
    if (ids.length) $('#playSrc').onclick = () => { setQueue(ids, 0, { view: 'source', name }); playAt(0); };
    v.querySelector('[data-go]').onclick = () => navTo('sources', null);
    bindSongRows(v); return;
  }
  const kw = q.trim().toLowerCase();
  if (!kw) { renderHome(); return; }
  const hitSongs = [], hitSingers = [], hitAlbums = [];
  for (const r of S.tracks) {
    if (r.n.toLowerCase().includes(kw)) hitSongs.push(r.i);
    if (hitSongs.length > 400) break;
  }
  S.singers.forEach(s => { if (s.name.toLowerCase().includes(kw)) hitSingers.push(s); });
  S.albums.forEach(a => { if (a.name.toLowerCase().includes(kw)) hitAlbums.push(a); });
  v.innerHTML = `
    <div class="crumb"><span>搜索「${esc(q)}」</span></div>
    ${hitSingers.length ? `<section class="sec"><div class="sec-h"><h2>歌手</h2><span class="more">${hitSingers.length} 位</span></div>
      <div class="grid">${hitSingers.slice(0, 12).map(singerCard).join('')}</div></section>` : ''}
    ${hitAlbums.length ? `<section class="sec"><div class="sec-h"><h2>专辑</h2><span class="more">${hitAlbums.length} 张</span></div>
      <div class="grid">${hitAlbums.slice(0, 12).map(albumCard).join('')}</div></section>` : ''}
    <section class="sec"><div class="sec-h"><h2>歌曲</h2><span class="more">${hitSongs.length} 首</span></div>
      ${hitSongs.length ? `<div class="slist-head"><button class="big-play" id="playSs"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg></button><div class="info">播放全部搜索结果</div></div>` : ''}
      ${songListHTML(hitSongs, { ctx: 'search', ctxName: q })}</section>`;
  const b = $('#playSs'); if (b) b.onclick = () => { setQueue(hitSongs, 0, { view: 'search', q }); playAt(0); };
  bindCards(v); bindSongRows(v); bindMore(v, () => renderSearch(q));
}
function bindMore(v, fn) {
  v.querySelectorAll('[data-more]').forEach(b => b.onclick = () => { LIST_LIMIT += 300; fn(); });
}

/* ---------------- 快捷索引 ---------------- */
function idsBySinger(name) { return S.tracks.filter(r => r.s.split(/[、,，/&;；]+/).map(x => x.trim()).includes(name)).map(r => r.i); }
function idsByAlbum(name) { return S.tracks.filter(r => r.a === name).map(r => r.i); }
function idsBySource(name) { return S.tracks.filter(r => r.o === name).map(r => r.i); }

/* ---------------- 播放 ---------------- */
const audioEl = audio;
function setQueue(ids, at, ctx) {
  P.queue = ids.slice();
  P.qi = at;
  P.ctx = Object.assign({ ids }, ctx || {});
  renderQueue();
}
function playAt(at) {
  if (!P.queue.length) return;
  P.qi = ((at % P.queue.length) + P.queue.length) % P.queue.length;
  const id = P.queue[P.qi];
  P.cur = id;
  P.srcMode = 'direct';
  loadAndPlay(id);
  markPlaying();
}
function loadAndPlay(id) {
  const r = S.tracks[id];
  setNowPlayingUI(r);
  fetch('/api/url?id=' + id).then(x => x.json()).then(res => {
    if (!res.ok && !res.url) throw new Error(res.note || 'no url');
    $('#pbSrc').textContent = res.viaCn || '';
    if (P.cur !== id) return;
    audioEl.src = res.url;
    P.srcMode = 'direct';
    audioEl.play().catch(() => { });
    $('#pbSrc').title = res.note || '';
  }).catch(() => {
    P.srcMode = 'proxy';
    audioEl.src = '/api/proxy?id=' + id + '&force=1';
    audioEl.play().catch(() => toast('该曲目暂无法播放'));
  });
  api('/api/recent', { id });
}
audioEl.addEventListener('error', () => {
  if (P.cur < 0 || !audioEl.src) return;
  if (P.srcMode === 'direct') {
    P.srcMode = 'proxy';
    toast('直连受阻，切换代理通道…');
    audioEl.src = '/api/proxy?id=' + P.cur + '&force=1';
    audioEl.play().catch(() => { });
  } else if (P.srcMode === 'proxy') {
    P.srcMode = 'dead';
    toast('❌ 音源已失效，自动跳过');
    setTimeout(() => next(true), 800);
  }
});
audioEl.addEventListener('play', () => { $('#icoPlay').innerHTML = '<path d="M6 5h4v14H6zm8 0h4v14h-4z"/>'; $('#plDisc').classList.add('spin'); });
audioEl.addEventListener('pause', () => { $('#icoPlay').innerHTML = '<path d="M8 5v14l11-7z"/>'; $('#plDisc').classList.remove('spin'); });
audioEl.addEventListener('timeupdate', onTime);
audioEl.addEventListener('loadedmetadata', onTime);
audioEl.addEventListener('ended', () => {
  if (P.mode === 'one') { audioEl.currentTime = 0; audioEl.play(); return; }
  next(true);
});

function setNowPlayingUI(r) {
  if (!r) return;
  $('#pbName').textContent = r.n; $('#pbArtist').textContent = r.s;
  $('#pbCover').querySelector('img').src = coverOf(r);
  $('#pbCover').querySelector('img').dataset.i = r.i;
  $('#plCover').src = coverOf(r);
  $('#plBg').style.backgroundImage = `url("${coverOf(r)}"), url("/assets/playbg_dai.png")`;
  $('#plTitle').textContent = r.n; $('#plArtist').textContent = r.s;
  $('#plAlbum').textContent = r.a ? '专辑 · ' + r.a : '';
  $('#btnLike').classList.toggle('liked', S.fav.has(r.i));
  loadLyric(r.i);
  renderQueue();
  markPlaying();
  syncPlayUI();
}
function markPlaying() {
  $$('.srow').forEach(x => x.classList.toggle('on', +x.dataset.i === P.cur));
}
function syncPlayUI() {
  const r = S.tracks[P.cur];
  $('#btnLike').classList.toggle('liked', !!(r && S.fav.has(r.i)));
  const modes = { list: '列表循环', one: '单曲循环', shuffle: '随机播放' };
  $('#btnMode').title = modes[P.mode];
  $('#btnMode').classList.toggle('on', P.mode !== 'list');
  $('#btnMode').querySelector('svg').innerHTML = P.mode === 'one'
    ? '<path d="M7 7h10v3l4-4-4-4v3H5v6h2zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2z"/>'
    : P.mode === 'shuffle' ? '<path d="M10 10 5 5H2v3l5 5zm0 4-5 5H2v-3l5-5zM17 7V4l5 5-5 5v-3h-3l-3-3h6zm0 10h-6l-2-2-2 2 3 3h7v3l5-5-5-5z"/>'
      : '<path d="M7 7h10v3l4-4-4-4v3H5v6h2zm10 10H7v-3l-4 4 4 4v-3h12v-6h-2z"/>';
}
function next(auto) {
  if (!P.queue.length) return;
  if (P.mode === 'shuffle') playAt(Math.floor(Math.random() * P.queue.length));
  else playAt(P.qi + 1);
}
function prev() {
  if (!P.queue.length) return;
  if (audioEl.currentTime > 4) { audioEl.currentTime = 0; return; }
  playAt(P.qi - 1);
}
$('#btnPlay').onclick = () => {
  if (!P.cur || P.cur < 0) { if (P.queue.length) playAt(P.qi < 0 ? 0 : P.qi); else { const ids = S.tracks.slice(0, 60).map(t => t.i); setQueue(ids, 0, { view: 'home' }); playAt(0); } return; }
  audioEl.paused ? audioEl.play() : audioEl.pause();
};
$('#btnNext').onclick = () => next();
$('#btnPrev').onclick = prev();
$('#btnMode').onclick = () => {
  P.mode = P.mode === 'list' ? 'one' : P.mode === 'one' ? 'shuffle' : 'list';
  syncPlayUI(); api('/api/settings', { mode: P.mode });
  toast({ list: '列表循环', one: '单曲循环', shuffle: '随机播放' }[P.mode]);
};
$('#vol').oninput = e => { P.vol = e.target.value / 100; audioEl.volume = P.vol; };
$('#vol').onchange = () => api('/api/settings', { volume: P.vol });
$('#btnVol').onclick = () => { const t = P.vol > 0 ? 0 : 0.8; P.vol = t; audioEl.volume = t; $('#vol').value = t * 100; };
$('#btnLike').onclick = () => { if (P.cur >= 0) toggleFav(P.cur); };
$('#pbCover').onclick = $('#pbName').onclick = () => openPlayer();
function togglePlayer(on) {
  const p = $('#player');
  const open = on == null ? !p.classList.contains('open') : !!on;
  p.classList.toggle('open', open);
  document.body.classList.toggle('full-player', open);
  $('#btnLyric').classList.toggle('on', open);
}
$('#btnLyric').onclick = () => togglePlayer();
$('#plClose').onclick = () => togglePlayer(false);
$('#btnQueue').onclick = () => { $('#queue').classList.toggle('open'); };
$('#qClear').onclick = () => { setQueue([], 0, {}); audioEl.pause(); audioEl.removeAttribute('src'); P.cur = -1; $('#pbName').textContent = '未播放'; $('#pbArtist').textContent = '—'; };
function openPlayer() { togglePlayer(true); }

function onTime() {
  const d = audioEl.duration || (S.tracks[P.cur] ? S.tracks[P.cur].d : 0) || 0;
  const t = audioEl.currentTime || 0;
  $('#tCur').textContent = fmtTime(t); $('#tAll').textContent = fmtTime(d);
  const pct = d ? (t / d * 100) : 0;
  $('#pbProgIn').style.width = pct + '%';
  $('#pbProgDot').style.left = pct + '%';
  if (window._lrc) syncLyric(t);
}
$('#pbProg').onclick = e => {
  const r = $('#pbProg').getBoundingClientRect();
  const p = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
  if (audioEl.duration) audioEl.currentTime = p * audioEl.duration;
};

function toggleFav(i) {
  const on = !S.fav.has(i);
  if (on) S.fav.add(i); else S.fav.delete(i);
  $('#cntFav').textContent = S.fav.size;
  api('/api/fav', { id: i, on });
  toast(on ? '已加入我喜欢的音乐' : '已从我喜欢的移除');
  $$('.srow').forEach(x => {
    if (+x.dataset.i === i) {
      const b = x.querySelector('[data-act="like"]');
      if (b) b.classList.toggle('on', on);
    }
  });
  if (P.cur === i) $('#btnLike').classList.toggle('liked', on);
  if (H.stack[H.pos] === 'fav|') renderByKey('fav', '');
}

/* ---------------- 歌词 ---------------- */
function loadLyric(i) {
  window._lrc = null; syncLyricFlag = true;
  $('#plLyric').innerHTML = '<p class="ph">歌词加载中…</p>';
  fetch('/api/lyric?id=' + i).then(x => x.json()).then(d => {
    if (P.cur !== i) return;
    const lrc = parseLrc(d.lrc);
    if (!lrc.length) { $('#plLyric').innerHTML = '<p class="ph">纯音乐，请欣赏</p>'; window._lrc = null; return; }
    window._lrc = lrc;
    $('#plLyric').innerHTML = lrc.map((l, k) => `<p data-k="${k}">${esc(l.txt) || '&nbsp;'}</p>`).join('');
    $('#plLyric').scrollTop = 0;
    $('#plLyric')._k = -1;
  }).catch(() => { $('#plLyric').innerHTML = '<p class="ph">歌词获取失败</p>'; });
}
let syncLyricFlag = false;
function parseLrc(txt) {
  if (!txt) return [];
  const out = [];
  for (const line of String(txt).split(/\r?\n/)) {
    const m = [...line.matchAll(/\[(\d{1,2}):(\d{1,2})(?:[.:](\d{1,3}))?\]/g)];
    if (!m.length) continue;
    const text = line.replace(/\[[^\]]*\]/g, '').trim();
    for (const x of m) {
      const t = (+x[1]) * 60 + (+x[2]) + (+(x[3] || 0)) / (String(x[3] || '').length === 3 ? 1000 : 100);
      out.push({ t, txt: text });
    }
  }
  return out.sort((a, b) => a.t - b.t).map(o => ({ t: o.t, txt: o.txt }));
}
function syncLyric(cur) {
  const lrc = window._lrc; if (!lrc || !lrc.length) return;
  let k = 0;
  for (let i = 0; i < lrc.length; i++) { if (lrc[i].t <= cur + 0.25) k = i; else break; }
  const box = $('#plLyric');
  const ps = box.querySelectorAll('p');
  if (box._k === k) return;
  box._k = k;
  ps.forEach((p, i) => p.classList.toggle('cur', i === k));
  const t = ps[k];
  if (t) box.scrollTop = t.offsetTop - box.clientHeight / 2 + t.clientHeight / 2;
}

/* ---------------- 播放队列 ---------------- */
function renderQueue() {
  const L = $('#qList');
  $('#qCount').textContent = P.queue.length ? `${P.qi + 1} / ${P.queue.length}` : '';
  const CAP = 400;   // 队列可能上万首(播放全部), 只渲染前若干条避免卡顿
  const head = P.queue.slice(0, CAP);
  L.innerHTML = head.map((i, k) => {
    const r = S.tracks[i]; if (!r) return '';
    return `<div class="q-row ${i === P.cur ? 'on' : ''}" data-q="${k}"><span class="qs">${esc(r.s)}</span><span class="qn">${k + 1}. ${esc(r.n)}</span><span class="qs">${r.d ? fmtTime(r.d) : ''}</span></div>`;
  }).join('') + (P.queue.length > CAP ? `<div class="q-row" style="color:#9AA2AE;cursor:default">…还有 ${P.queue.length - CAP} 首未列出</div>` : '');
  L.querySelectorAll('.q-row').forEach(n => n.onclick = () => playAt(+n.dataset.q));
}

/* ---------------- 右键菜单 ---------------- */
function openCtx(e, i) {
  ctxMenuId = i;
  const m = $('#ctxmenu');
  const r = S.tracks[i];
  m.innerHTML = `
    <div data-c="play"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>立即播放</div>
    <div data-c="next"><svg viewBox="0 0 24 24"><path d="M16 6h2v12h-2zM6 6l9 6-9 6z"/></svg>下一首播放</div>
    <hr>
    <div data-c="like"><svg viewBox="0 0 24 24"><path d="M12 21s-8-5.1-8-10.4A4.6 4.6 0 0 1 12 7a4.6 4.6 0 0 1 8 3.6C20 15.9 12 21 12 21"/></svg>${S.fav.has(i) ? '取消喜欢' : '喜欢这首歌'}</div>
    <div data-c="addto"><svg viewBox="0 0 24 24"><path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z"/></svg>添加到歌单</div>
    <hr>
    <div data-c="artist"><svg viewBox="0 0 24 24"><path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8m0 2c-4 0-8 2-8 4.5V21h16v-2.5C20 16 16 14 12 14"/></svg>查看歌手：${esc((r.s || '').slice(0, 12))}</div>
    <div data-c="album"><svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20m0 13a3 3 0 1 1 0-6 3 3 0 0 1 0 6"/></svg>查看专辑</div>
    <hr><div class="sub" data-c="info">音源：${esc(r.o)} · ${esc(r.x || '')}</div>`;
  m.classList.add('open');
  const w = 200, h = m.offsetHeight || 250;
  m.style.left = Math.min(e.clientX, innerWidth - w - 8) + 'px';
  m.style.top = Math.min(e.clientY, innerHeight - h - 90) + 'px';
  m.onclick = ev => {
    const c = ev.target.closest('[data-c]'); if (!c) return;
    const i2 = ctxMenuId; m.classList.remove('open');
    const a = c.dataset.c;
    if (a === 'play') { const list = (P.ctx.ids && P.ctx.ids.includes(i2)) ? P.ctx.ids : [i2]; const at = list.indexOf(i2); setQueue(list, at < 0 ? 0 : at, P.ctx); playAt(at < 0 ? 0 : at); }
    else if (a === 'next') { P.queue.splice(P.qi + 1, 0, i2); renderQueue(); toast('已加入下一首播放'); }
    else if (a === 'like') toggleFav(i2);
    else if (a === 'addto') pickPlaylist(i2);
    else if (a === 'artist') navTo('artist', S.tracks[i2].s.split(/[、,，/&;；]+/)[0].trim());
    else if (a === 'album') { if (S.tracks[i2].a) navTo('album', S.tracks[i2].a); }
  };
}
document.addEventListener('click', e => { if (!e.target.closest('#ctxmenu')) $('#ctxmenu').classList.remove('open'); });

/* ---------------- 歌单 ---------------- */
function renderPlaylists() {
  const box = $('#plList');
  if (!S.playlists.length) { box.innerHTML = '<div class="empty">还没有歌单</div>'; }
  else box.innerHTML = S.playlists.map(p => `<a data-pid="${esc(p.id)}" class="${H.stack[H.pos] === 'playlist|' + p.id ? 'on' : ''}">
      <svg viewBox="0 0 24 24"><path d="M4 5h16v2H4zm0 6h10v2H4zm0 6h16v2H4zm14-6v6.2a2.2 2.2 0 1 1-2-2.2V9h4v2z"/></svg>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(p.name)}</span>
      <span class="del" title="删除"><svg viewBox="0 0 24 24"><path d="M19 6.4 17.6 5 12 10.6 6.4 5 5 6.4 10.6 12 5 17.6 6.4 19 12 13.4 17.6 19 19 17.6 13.4 12z"/></svg></span></a>`).join('');
  box.querySelectorAll('a').forEach(a => {
    a.onclick = e => {
      if (e.target.closest('.del')) {
        e.stopPropagation();
        const pl = S.playlists.find(p => p.id === a.dataset.pid);
        confirmBox('删除歌单', `确定删除《${pl.name}》吗？`, () => api('/api/playlist', { op: 'delete', id: a.dataset.pid }).then(r => { if (r.ok) { S.playlists = r.playlists; renderPlaylists(); if (H.stack[H.pos] === 'playlist|' + a.dataset.pid) navTo('home', null); } }));
        return;
      }
      navTo('playlist', a.dataset.pid);
    };
  });
  $('#cntFav').textContent = S.fav.size;
}
$('#btnNewPl').onclick = () => askName('新建歌单', '', n => api('/api/playlist', { op: 'create', name: n }).then(r => { if (r.ok) { S.playlists = r.playlists; renderPlaylists(); navTo('playlist', r.id); } }));
function pickPlaylist(sid) {
  const m = $('#modal');
  $('#modalBox').innerHTML = `<h3>添加到歌单</h3>
    <div class="pl-pick">${S.playlists.map(p => `<div data-pid="${esc(p.id)}"><svg viewBox="0 0 24 24" style="width:15px;height:15px"><path d="M4 5h16v2H4zm0 6h10v2H4zm0 6h16v2H4zm14-6v6.2a2.2 2.2 0 1 1-2-2.2V9h4v2z"/></svg>${esc(p.name)}<span style="margin-left:auto;color:#9AA2AE;font-size:11px">${p.ids.length} 首</span></div>`).join('') || '<div style="color:#9AA2AE;padding:10px">还没有歌单，先新建一个</div>'}</div>
    <div class="mb"><button class="cancel">取消</button><button class="ok">新建歌单</button></div>`;
  m.classList.add('open');
  $('#modalBox').querySelector('.cancel').onclick = () => m.classList.remove('open');
  $('#modalBox').querySelector('.ok').onclick = () => { m.classList.remove('open'); askName('新建歌单', '', n => api('/api/playlist', { op: 'create', name: n }).then(r => { if (r.ok) { S.playlists = r.playlists; renderPlaylists(); api('/api/playlist', { op: 'add', id: r.id, sid }).then(r2 => { S.playlists = r2.playlists; renderPlaylists(); toast('已添加到新歌单'); }); } })); };
  $('#modalBox').querySelectorAll('[data-pid]').forEach(d => d.onclick = () => {
    api('/api/playlist', { op: 'add', id: d.dataset.pid, sid }).then(r => {
      if (r.ok) { S.playlists = r.playlists; renderPlaylists(); }
      toast('已添加到歌单'); m.classList.remove('open');
    });
  });
}

/* ---------------- 小工具 ---------------- */
async function api(url, body) {
  try {
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    return await r.json();
  } catch (e) { return { ok: false }; }
}
let toastTimer;
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 2000);
}
function askName(title, val, cb) {
  const m = $('#modal');
  $('#modalBox').innerHTML = `<h3>${esc(title)}</h3><input id="mIn" maxlength="24" placeholder="输入名称" value="${esc(val)}">
    <div class="mb"><button class="cancel">取消</button><button class="ok">确定</button></div>`;
  m.classList.add('open');
  const inp = $('#mIn'); inp.focus(); inp.select();
  const go = () => { const n = inp.value.trim(); if (!n) { inp.focus(); return; } m.classList.remove('open'); cb(n); };
  $('#modalBox').querySelector('.cancel').onclick = () => m.classList.remove('open');
  $('#modalBox').querySelector('.ok').onclick = go;
  inp.onkeydown = e => { if (e.key === 'Enter') go(); if (e.key === 'Escape') m.classList.remove('open'); };
}
function confirmBox(title, text, cb) {
  const m = $('#modal');
  $('#modalBox').innerHTML = `<h3>${esc(title)}</h3><p style="color:#6A7280;font-size:13.5px;margin:0 0 6px">${esc(text)}</p>
    <div class="mb"><button class="cancel">取消</button><button class="ok" style="background:#C8452F">删除</button></div>`;
  m.classList.add('open');
  $('#modalBox').querySelector('.cancel').onclick = () => m.classList.remove('open');
  $('#modalBox').querySelector('.ok').onclick = () => { m.classList.remove('open'); cb(); };
}

/* ---------------- 搜索与快捷键 ---------------- */
let qTimer;
$('#q').oninput = e => {
  clearTimeout(qTimer);
  const v = e.target.value;
  qTimer = setTimeout(() => {
    if (!v.trim()) { renderByKey('home', ''); return; }
    H.stack = H.stack.slice(0, H.pos + 1); H.stack.push('search|' + v); H.pos = H.stack.length - 1;
    $$('#navMain a, #navMine a').forEach(a => a.classList.remove('on'));
    renderSearch(v);
  }, 220);
};
$('#q').onkeydown = e => { if (e.key === 'Escape') { e.target.value = ''; renderByKey('home', ''); e.target.blur(); } };
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === '/') { e.preventDefault(); $('#q').focus(); return; }
  if (e.code === 'Space') { e.preventDefault(); $('#btnPlay').click(); }
  else if (e.key === 'ArrowRight' && e.ctrlKey) next();
  else if (e.key === 'ArrowLeft' && e.ctrlKey) prev();
  else if (e.key === 'ArrowUp') { $('#vol').value = Math.min(100, +$('#vol').value + 5); $('#vol').oninput({ target: $('#vol') }); }
  else if (e.key === 'ArrowDown') { $('#vol').value = Math.max(0, +$('#vol').value - 5); $('#vol').oninput({ target: $('#vol') }); }
});
window.addEventListener('beforeunload', () => { try { navigator.sendBeacon && navigator.sendBeacon('/api/settings', new Blob([JSON.stringify({ volume: P.vol, mode: P.mode })], { type: 'application/json' })); } catch (e) { } });
