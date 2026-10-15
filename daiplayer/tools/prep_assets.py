# -*- coding: utf-8 -*-
"""把 ImageGen 原始 PNG 转成体积可控的素材: 图标(ico+png) / banner / 默认封面。"""
import os, io, glob
from PIL import Image

SRC = r'D:\air\qqbuddy\mountainriverechoes\daiplayer\assets'
OUT = os.path.join(SRC, 'ui')
os.makedirs(OUT, exist_ok=True)

log = io.open(r'D:\air\qqbuddy\mountainriverechoes\daiplayer\_prep_assets.txt', 'w', encoding='utf-8')
def w(*a): log.write(' '.join(str(x) for x in a) + '\n')

pngs = sorted(glob.glob(os.path.join(SRC, '*.png')))
for p in pngs:
    w('%.2f MB  %s' % (os.path.getsize(p)/1048576.0, os.path.basename(p)))

def pick(kw):
    for p in pngs:
        n = os.path.basename(p).lower()
        if all(k in n for k in kw):
            return p
    return None

f_icon    = pick(['app_icon'])
f_banner  = pick(['wide_banner'])
f_peacock = pick(['close_'])     # peacock feathers
# 两张同前缀: 16-26-25 = 象脚鼓, 16-26-41 = 葫芦丝
f_drum    = pick(['a_dai', '16-26-25'])
f_water   = pick(['dai_w'])
f_hulusi  = pick(['a_dai', '16-26-41'])

w('\nmapping:')
for k, v in (('icon', f_icon), ('banner', f_banner), ('peacock', f_peacock), ('drum', f_drum), ('water', f_water), ('hulusi', f_hulusi)):
    w('  ', k, '->', os.path.basename(v) if v else None)

def dewatermark(im, rx=0.945, ry=0.93):
    """ImageGen 输出右下角带 'AI生成/WORKBUDDY' 角标 —— 裁掉右下边缘即可去掉, 比例变化 <2% 无感。"""
    W, H = im.size
    return im.crop((0, 0, int(W * rx), int(H * ry)))


def save_jpg(src, dst, size, q=82):
    im = dewatermark(Image.open(src).convert('RGB'))
    im = im.resize(size, Image.LANCZOS)
    im.save(dst, 'JPEG', quality=q, optimize=True, progressive=True)
    w('   saved %-28s %.2f MB' % (os.path.basename(dst), os.path.getsize(dst)/1048576.0))

# 1) App 图标: 256 png + ico
if f_icon:
    im = Image.open(f_icon).convert('RGBA')
    W, H = im.size
    im = im.crop((0, 0, int(W * 0.90), int(H * 0.90)))   # 去右下角水印
    im256 = im.resize((256, 256), Image.LANCZOS)
    im256.save(os.path.join(OUT, 'icon.png'), 'PNG', optimize=True)
    im256.save(os.path.join(OUT, 'app.ico'), 'ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])
    w('   saved icon.png / app.ico  %.2f MB / %.2f MB' % (
        os.path.getsize(os.path.join(OUT,'icon.png'))/1048576.0,
        os.path.getsize(os.path.join(OUT,'app.ico'))/1048576.0))

# 2) banner 横幅 1400x520 (16:6 裁切)
if f_banner:
    im = dewatermark(Image.open(f_banner).convert('RGB'), 0.985, 0.985)
    tw, th = 1400, 520
    r = max(tw/im.width, th/im.height)
    im2 = im.resize((int(im.width*r)+1, int(im.height*r)+1), Image.LANCZOS)
    l = (im2.width - tw)//2; t = max(0, (im2.height - th)//3)
    im2 = im2.crop((l, t, l+tw, t+th))
    im2.save(os.path.join(OUT, 'banner.jpg'), 'JPEG', quality=80, optimize=True, progressive=True)
    w('   saved banner.jpg %.2f MB' % (os.path.getsize(os.path.join(OUT,'banner.jpg'))/1048576.0))

# 3) 4 张默认专辑封面 480x480
for key, f in (('cover_peacock', f_peacock), ('cover_drum', f_drum), ('cover_water', f_water), ('cover_hulusi', f_hulusi)):
    if f:
        save_jpg(f, os.path.join(OUT, key + '.jpg'), (480, 480), 80)

# 4) 播放页背景(模糊大图)
if f_peacock:
    im = dewatermark(Image.open(f_peacock).convert('RGB')).resize((900, 900), Image.LANCZOS)
    im.save(os.path.join(OUT, 'playbg.jpg'), 'JPEG', quality=72, optimize=True, progressive=True)
    w('   saved playbg.jpg %.2f MB' % (os.path.getsize(os.path.join(OUT,'playbg.jpg'))/1048576.0))

w('\n--- ui dir ---')
tot = 0
for p in sorted(glob.glob(os.path.join(OUT, '*'))):
    tot += os.path.getsize(p)
    w('  %.2f MB  %s' % (os.path.getsize(p)/1048576.0, os.path.basename(p)))
w('  TOTAL %.2f MB' % (tot/1048576.0))
log.close()
print('ok')
