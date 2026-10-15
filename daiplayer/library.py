# -*- coding: utf-8 -*-
"""傣音廊 · 曲库层
==================
从 `e16_傣族.json`(山河回响·傣族库导出) 载入 8751 首曲目, 构建前端所需轻量索引。

设计要点:
- 原始 JSON 里每条 track 有 `_song`(完整 SongInfo) 与一组展示字段; 播放只需要 `_song.download_url`
  和 `identifier`, 其余全部投影成短键索引, 把 29MB 压到 ~1.3MB 便于一次性下发给前端。
- 数据文件与用户状态分离: 曲库只读, 收藏/歌单/播放记录写 %APPDATA%\\DaiMusic\\state.json。
"""
import io
import os
import re
import json
import time
import threading
from pathlib import Path

APP_NAME = 'DaiMusic'


# ---------------------------------------------------------------- 路径

def app_dir() -> Path:
    """应用根目录: 打包后为 exe 所在目录, 开发时为源码目录。"""
    import sys
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def data_dir() -> Path:
    """用户数据目录(%APPDATA%\\DaiMusic)。"""
    base = os.environ.get('APPDATA') or os.path.expanduser('~')
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_library_path() -> Path:
    """按优先级定位曲库 JSON。"""
    cands = []
    if os.environ.get('DAI_LIBRARY'):
        cands.append(Path(os.environ['DAI_LIBRARY']))
    root = app_dir()
    cands += [
        root / 'data' / 'e16_傣族.json',
        root / 'e16_傣族.json',
    ]
    import sys
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        cands.append(Path(sys._MEIPASS) / 'data' / 'e16_傣族.json')
    # 开发态: 上游仓库路径
    cands += [
        Path(r'D:\e16_傣族.json'),
        Path(r'D:\air\qqbuddy\mountainriverechoes\webui\ethnos_cache\e16_傣族.json'),
        Path(r'D:\air\qqbuddy\mountainriverechoes\e16_傣族.json'),
    ]
    for c in cands:
        try:
            if c.is_file() and c.stat().st_size > 1024:
                return c
        except OSError:
            continue
    raise FileNotFoundError('未找到曲库文件 e16_傣族.json, 已尝试:\n' + '\n'.join(str(c) for c in cands))


# ---------------------------------------------------------------- 傣族筛选
# 曲库来自「山河回响·傣族(e16)」子库, 经关键词检索抓取, 混入了大量非傣族内容:
# 其他民族歌曲、流行翻唱、DJ/喊麦混音、B站视频/有声书、影视综艺片段等。
# 判定优先级(先命中先返回):
#   1. 人工精确删除(逐曲核对过的曲目/歌手+曲目对)
#   2. 视频源(B站BV号)/有声书评书连载 -> 删(不是歌曲)
#   3. DJ/喊麦/phonk/抖音BGM/混音噪声 -> 删
#   4. 明确傣族信号: 含"傣"/傣泰掸老文字 -> 留
#   5. 傣族经典曲目名(月光下的凤尾竹/婚誓/泼水节/赶摆/章哈...) -> 留
#   6. 傣族专辑名(章哈/民语/出洼干朵/赛卯/Tai·Shan Songs...) -> 留
#   7. 已核实的垃圾歌手 -> 删
#   8. 非音乐内容(影视插曲/教学简谱/助眠冥想/钢琴古筝翻奏...) -> 删
#   9. 其他民族族名/地域标记 -> 删
#   10. 其余默认保留(本库为傣族库, 存疑项从宽保留, 宁留勿误删)
NON_DAI_TOKENS = [
    '回族', '回民', '汉族', '彝族', '彝语', '彝族舞曲', '藏族', '藏语', '维吾尔', '维族', '蒙古族', '蒙语',
    '哈萨克', '苗族', '壮族', '布依', '朝鲜族', '满族', '侗族', '瑶族', '白族', '土家族', '傈僳族',
    '佤族', '拉祜', '纳西族', '景颇', '哈尼族', '高山族', '撒拉', '羌族', '布朗族', '阿昌族', '德昂族',
    '普米', '基诺族', '怒族', '保安族', '裕固', '京族', '塔吉克', '独龙', '鄂温克', '鄂伦春', '赫哲',
    '门巴', '珞巴', '俄罗斯族', '锡伯', '仫佬', '毛南', '仡佬', '土族', '东乡', '水族', '畲族',
    '新疆', '西藏', '拉萨', '陕北', '江南', '青海', '甘肃', '信天游', '草原歌曲', '长调', '呼麦',
    '木卡姆', '格萨尔', '梨园戏', '越剧', '黄梅戏', '豫剧', '评剧', '昆曲',
]

# 视频源/有声书: 不是歌曲
BV_RE = re.compile(r'BV[0-9A-Za-z]{8,}')
EP_RE = re.compile(
    r'第\s*\d+\s*[集回章部季话]|[-\s_（(]\d+\s*[集回][-\s_）)]|集全|全集|有声书|评书|广播剧|'
    r'相声|有声演播|有声小说|有声剧|多人有声|多播|爽文|穿越都市|玄幻')

# 混音噪声: 即使带傣族信号也删(不是原曲)
JUNK_GENRE = [
    '喊麦', 'DJ', 'dj', 'D.J', 'phonk', 'Phonk', 'PHONK', '重低音', '抖音', '快手', '热播',
    'BGM', 'bgm', '电音', '慢摇', '舞曲', '进行曲', 'Remix', 'remix', 'RIMIX', 'Rimix',
    '卡点', '变速', '车载', '酒吧', '包厢', 'MC', '土味', '精神小伙', '社会摇', '硬曲',
    '重鼓', '迷幻', '咚鼓', 'Q鼓', '昆曲', '京剧', '野迪',
]

# 非音乐内容: 教学/伴奏/影视综艺/助眠/器乐翻奏等(傣族经典曲目名优先, 故排在其后)
JUNK_CONTENT = [
    '动漫', '二次元', '动画', '漫画', '游戏', '原神', '英雄联盟', '王者', '第五人格', '我的世界',
    '小说', '推文', '短剧', '电视剧', '电影', '插曲', '主题曲', '片尾曲', '综艺', '晚会', '春晚',
    '演唱会', 'MV', '舞剧', '考级', '教学', '教程', '入门', '简谱', '视唱', '动态谱', '纯伴奏',
    '助眠', '催眠', '冥想', '养生', '治疗音乐', 'SPA', '钢琴', '古筝', '吉他', '小提琴', '萨克斯',
    '扬琴', '古琴', '琵琶', '口琴', '电钢', 'MIDI', 'midi', '铃声', '彩铃', '外卖', '导航',
    '广场舞', '儿歌', '童谣', '朗诵', '古诗', '诗词', '鬼故事', '恐怖', '灵异', '悬疑', '健身',
    '瑜伽', '理发店', '学科', '考研', '艺考', '公开课', '有声', '直播', 'Cover', 'cover', 'COVER',
    'Tribute', 'vlog', 'Vlog', 'VLOG', '短视频',
]

# 傣族经典曲目名/乐器/节庆/地名: 命中即视为傣族音乐
DAI_CLASSICS = [
    '月光下的凤尾竹', '有一个美丽的地方', '婚誓', '竹林深处', '多情的巴乌', '金色的孔雀',
    '金色的口弦', '赶摆归来', '嘎伴光', '喊伴光', '泼水', '水节', '开门节', '关门节', '竹楼',
    '葫芦丝', '象脚鼓', '章哈', '贝叶', '出洼', '干朵', '遮放', '摩雅傣', '召树屯',
    '喃木诺娜', '紧那罗', '金孔雀', '胞波', '瑞丽江', '巴乌', '崴萨啰', '崴萨罗', '哨哆哩',
    '猫哆哩', '小卜少', '卜少', '凤尾竹', '缅桂', '勐', '版纳', '西双版纳', '德宏', '瑞丽',
    '芒市', '耿马', '孟连', '勐海', '勐腊', '景洪', '景谷', '澜沧', '盈江', '陇川', '梁河',
    '嘎洒', '橄榄坝', '告庄', '勐遮', '打洛', '勐卧', '勐梭', '勐马', '勐焕', '勐卯', '弄岛',
    '畹町', '木姐', '南坎', '芒允', '南垒河', '章芭', '傣味', '赶摆', '嘎光', '象脚', '孔雀舞',
]

# 傣族专辑名: 命中即保留
DAI_ALBUMS = [
    '章哈', '泼水节', '民语', '出洼', '干朵', '赛卯', 'Tai Song', 'Shan Song', 'Water Festival',
    '葫芦丝', '赶摆', '傣味', '勐巴娜西', '章芭', '月光下的凤尾竹', '有一个美丽的地方',
    '竹林深处', '多情的巴乌', '婚誓', '金色的孔雀', '金色的口弦', '德宏', '版纳', '瑞丽',
]

# 人工确认要删除的曲目(按标题精确匹配, 已逐条核对不会误伤傣族歌曲):
REMOVE_TITLES = {
    # 藏族题材
    '通往天路的哈达', '青藏高原（翻唱）',
    # 古诗词题材
    '念奴娇(一)',
    # 普通话流行歌(宝玉 / 黄玉娇)
    '世界风的碰撞', '别在伤口撒盐', '归来', '不做痴情人',
    '输了你赢了世界又如何M2', '往后余生',
    # 蒙古族题材
    '敖包相会 (三步踩版)', '欢乐的那达慕', '美丽的草原我的家', '美丽的草原美丽的姑娘',
    # 京剧版 / 儿歌
    '沧海一声笑 (京剧版)', '金色的小船',
    # 昆曲(用户点名删除)
    '昆曲 长生殿•小宴选段-方莛玉 - video_20260922_200132',
}

# 人工逐曲删除(歌手名+标题精确对): 用于同一歌手名下混有非傣族曲目的情况
REMOVE_TRACKS = {
    # 石玉环: 专辑名为傣族经典, 但仅《月光下的凤尾竹》本身是傣族歌曲
    ('石玉环', '阿佤人民唱新歌'), ('石玉环', '星星索'), ('石玉环', '北国之春'),
    ('石玉环', '常回家看看'),
    # 岩温斌斌: 傣族歌手, 但这几首是藏语/红歌/影视翻唱
    ('岩温斌斌', '草原迎宾曲(男声版)'), ('岩温斌斌', '女儿情(男版)'), ('岩温斌斌', '桑吉卓玛'),
    ('岩温斌斌', '敬你一碗青稞酒'), ('岩温斌斌', '毛委员和我们在一起'),
    ('岩温斌斌', '长街晏'), ('岩温斌斌', '感恩歌'), ('岩温斌斌', '别在金秋'),
    # 三明葫芦丝: 流行翻奏(保留其《让我听懂你的语言》傣族曲)
    ('三明葫芦丝', '心相印手牵手 (翻奏 杨钰莹)'), ('三明葫芦丝', '小小新娘花 (翻奏 大阿文)'),
    ('三明葫芦丝', '回娘家'), ('三明葫芦丝', '苹果香 (六星街里) (翻奏 黑大婶回乡带哇)'),
    ('三明葫芦丝', '爱江山更爱美人 (翻奏 谭玥明)'), ('三明葫芦丝', '鸿雁（电子琴）'),
    # 华语群星: 葫芦丝CD里的非傣族民歌翻奏
    ('华语群星', '绿岛小夜曲'), ('华语群星', '乌苏里船歌'),
    # 群星: 非傣族翻唱/儿歌串烧
    ('群星', '神话'), ('群星', '爱你没有停止的一天'),
    ('群星', '两只老虎+蜜蜂做工+举你的右手摆一摆+我的朋友在那里+火车快车+郊游+小金鱼+数蛤蟆+萤火虫+拔罗卜+只要我长大+母鸭带小鸭+大骏马+捕鱼歌+小猴子=一个拇指动一动+蜗牛+丑小鸭+小毛驴+唱起歌'),
    # 艾山: 仅《月光下的勐遮坝》为傣族题材
    ('艾山', '向黄昏驶去'), ('艾山', 'yamgurluk kiqa'), ('艾山', '等你归来'),
    ('艾山', '从开始到现在'), ('艾山', '金色田园的承诺'),
    # 其它逐曲核对
    ('辰辰星期五', '基诺山歌-F调B调合奏-未知-岩宰伦奏'),
    ('半夏水玉', '目瑙纵歌'),
    ('民乐', '丽江美(竹笛)'),
    ('艾不乐', '天下足球之意甲二十年二十人'),
    ('三宝', '花腰歌舞'),
    ('鲜多多', '金色的屋檐（伤感版）'),
    # 长臂猿: 傣歌曲目保留, 流行翻唱删除
    ('长臂猿乐队', '你离开以后'), ('长臂猿乐队&符英生', '摇滚唢呐'),
    ('长臂猿&芒果奶奶绿', '冬眠（合唱版）'),
    # 未知歌手名下的杂项
    ('未知歌手', '(Cover)'), ('未知歌手', '(Special Version) (Explicit)'),
    ('未知歌手', '& PX'), ('未知歌手', 'Lux Brumalis'), ('未知歌手', '黑眼睛'),
    ('未知歌手', 'TOMBOY'), ('未知歌手', '下一个天亮'), ('未知歌手', '(Cover Version)'),
    ('未知歌手', '(Another Version)'), ('未知歌手', '(Explicit)'),
}

# 已核实的非傣族歌手(其全部曲目删除; 已排除含傣族经典曲目的歌手)
JUNK_SINGERS = {
    # 混音/DJ/喊麦
    '霏雨', 'DJ小可&霏雨', '电子致幻&霏雨', 'DJ阿金', 'DJ重炮', 'DJ小美', '欢乐的火箭筒鼓',
    # 电子/游戏音乐
    'Daeya', 'Daeya&Akeos', 'Skybreak, Daeya', 'Kotori, Daeya',
    'Ace Aura, Skybreak, Kotori, Daeya', 'Daeya, Quartzone', 'MAD DUBZ, Daeya, Jedwill',
    'Automhate, Daeya', 'KHUR', 'Khur', 'DDD', '付岩中', '提糯Tino, 哈利波特魔法觉醒',
    'Benny Oschmann, 哈利波特魔法觉醒', 'N2V', 'OneMusic Record', 'Noel Quinlan',
    '玉声泩/周俊成/逆水长琴/逆水寒/雷火音频',
    # 流行/翻唱
    '豆豆', '豆豆哥', 'The Saints', 'S.SA', 'Focus', '周杰伦', '李玟,周杰伦', '五月天',
    '徐小凤', '林忆莲', '周延英（英子-effie）', '陈乐基 Rocky Chan', 'Panta.Q 郭曲,Julia吴卓源',
    '张杰', '邓丽君', '王菲', '任贤齐', '郑伊健', '张学友', '梁静茹', '王杰', '朴树', '赵雷',
    '陈奕迅', '蔡健雅', '胡歌', '孙楠', '孙耀威', '郑钧', '温奕心', '张韶涵&周深', '大欢',
    '白小白', '全幺九', 'CPU王大锤', '温夏', '宇翼X', '112233依依', '韩路遥', 'Roice茹',
    '朱珠', '朱 珠', '朱珠侠', '郭金保', '何斐', '谢春花', '方锦龙', '林黛', '郎朗', '蒋才如',
    '陈博', '欢乐的吊钹', '欢乐的英国管', '韩路', 'Titan夏添', '霜序于兮', '欣蕊', '冯欣蕊',
    '冯欣蕊&瑞鸣音乐', '书欣蕊', '王欣蕊', '凌柒y, 王欣蕊', '谢军', '季骁萌', '优视书院',
    '小兴', '兴合唱团', '旅行新蜜蜂', '奥杰阿格', '好妹妹乐队&朱冰贞', '叶噶', '斌斌',
    '进之先生', '王丽达', '丁应康', '网络歌手&秦晓疯', '哈尔滨医科大学', '东方晴儿',
    '刘昊霖&Kidult', '吴雨霏', '糯米Nomi', 'Chris James', '艾山~~最浪', '艾山江·木合塔尔',
    '恩的', '酒糟乐队', '长臂猿', '宝矿力水特和长臂猿', 'SomeLove', '思安贵', '木森&孙兰妮',
    '阿YueYue', '谷雨', '王萌', '超凡音乐', '渔圈&徐艺莹', '舞曲', '童安格', '夏静寒',
    '李玲玉&苏珊&吴晶晶&吴静', '李玲玉', '腾尔玛', '九尾金小凤', 'Amit Saxena',
    'The Saint Johns', 'The Saint Orchestra', '洋菟&小可&小奶瓶', '么秀', 'AI音乐盲盒创作',
    '勒哈罗', '大锤', '叶尔波力·苏来别克', '郭富城', 'Eric周兴哲', '拉苏荣', '江逊之',
    '漂亮的笙', '太一神君', '小玉兰官方账号', '杨丽萍的舞蹈艺术', '动物之shen', '玫瑰',
    '李春波', '曹丽萍', '黑龙', '陈思思', '汪峰', '时嘉', '卢冠廷', '林慧萍', '罗志祥',
    '窦智孔', '韩红', 'JPM', '胡德夫', '关诗敏', '蒋薇', '许慧欣', '慢摇人生单曲循环',
    '小抠酥', '辛娜', '小意学姐', '刘德海', '爱看舞蹈的舞蹈搬运工', '肖玉', 'sharon暖玉',
    '韩泪玉', '玉米,加米娜', '洛颜如兰', '孟贵彬,马玉涛', 'YANA雅娜', '白玛多吉', '敖苏日娜',
    '好听的故事铺', '依养源健康管理', '波涛', '玉儿', '彩虹宝贝', '葛覃曦', 'Yingjun Guo',
    '伊能静', '王祖蓝', '唐古', '杨洪基', '郑绪岚', '冷漠', '吴倩莲', '林子娟', '何鹏, 冷漠',
    '唐建树', '叶蒨文', '戴玉强', '姚莉', '马兆骏', 'L（桃籽）', '安儿陈', '器乐组',
    '有智慧的帕格尼尼', '哈机咪', '声隅', '汪愉快的布祖基琴', '无言', '曾淑勤', '丁中罗',
    '欢乐的西特恩', 'Ennio Morricone', '天蝎猫李楚伦', 'Amanda', '金马小星星', '金旺旺',
    '兰卡措', '桑美兰', '布兰妮小镇', 'Kyle Xian', '上海交响乐团', '头号唢呐', '若芖_教师资格销吊中',
    # 短视频/直播/有声书账号
    '回忆加了分', '修道小鱼', '辉辉游戏解说', '盛炽_jingming', '壹匹白马_', '狗ROLL卷',
    '将无同的武夷岩茶', '恰空_PurrLude', 'CAD代画在线接单', '日记音乐', '音羽-otoha-',
    'jOOker777', '朵看动漫', '葛兰', '蔡佛缘', '白兰滴', '无名氏的小陈', '张德兰',
    '미란이 (MIRANI)', '西域刀郎', '阿兰', 'Faylan', '杨美兰', '刘霖,欧阳倩,张锦杰',
    '焦娇JoJo', '美玉', '金佩玉', '陈咏,陈娇', '锦玉', '杨娇', '民港', '陈玉建,陈娇',
    '巧妙绝伦', '中央乐团,马玉涛', '上官曼玉', '瞳光,TG王娇然,强怡衡', '心似如玉',
    '王二妮&云飞', 'Kawa乐队', '周志宏&杜俊辉&洪启峰&郭映秀&黄相勋&黄治评', '山歌丨',
    '我就是人lof', '小笛笛RUI', '刘音', '韵辉', '许之云', '黎奈Rinai', '恁道谎阳台雨云',
    '白石轩主', '摆摆忠', '三锅是女团研究僧', '金金不计较_哦', 'Makkishka', 'love小邪',
    '要早点睡oo', '俊采星驰舞美柒', '智恩enz', '爱贵州的李小脚', '夜雨知秋秋秋秋',
    '声音恋人', '苔花如米小', 'AI小懒', 'CV胖头鱼', '默依默依酱', '穗城珍珠',
    'agave龙蛇兰威名洁癖', '花雾浓w', '老花医', '劫小觉', '树林屹華', '纸喝office',
    '酥油面酱', 'TESTV官方频道', '磷酸2氢钾', '飞入依依', '寺崎香裕,近藤孝行,佐藤元',
    'DYSeven,SGod,Biggie', '路亦似舟', '西西', '路昊龙', '朱虹,陆路佳,陆剑萍', '铵澈',
    '路过1995ii', '路上井盖', '付路通', 'zyyy771188', '凌禄', '用户356837348', '王武超',
    '上仙', '悦光讲故事', '十三妖仙学院', '东道主', '果壳讲故事', 'XM梦回清河&喜马拉雅',
    '二次元小美', '声音爱跳舞', '郁郁佳城', '初昕有声', '一只月下君-', '兔子一声吼', '晴封',
    '泽国同学', '非影Q', 'CCCmlng小陈不憨', '巡人Y', '快乐阳光组委会', '中媒汇', 'Saw-cops',
    '猫meme睡不着', '外交部发言人办公室', '交通故事会-蛇王', '河南卫视', '寻人启事潮流版',
    '一只Oran之', '玄工志', '小明说驾车', 'Alpha机械师', '羊城晚报', '连句号都不能打',
    '小九爱干饭啊', '小倔驴MCN', '追剧真上头', '-玉现', '饭饭_KF', '一只木木木木马',
    '-Austins', '346833333', '金磁子', '陈小云', '沈孝', '沧桑小杰', '阿祥,金牌阿祥,DJ小阿郭',
    '阿祥、金牌阿祥、DJ小阿郭', '秦嘉宇,阿雷,朱志斌,百百五,日暮戈薇,周京泽,如果明天可以不下雨,上好佳,松影一庭,0505,小土,流文,小钰不是小喻,爱吃香菜,金蟾,绝纞,ぃんさん,小先生,葵花不葵.,春不晚',
    'Ml墨琳,雨宫凪,小明Kari,心爱Aria,白楼,长明hemosa,Dean球九,瀹宛,暮迟Kurechi,卿离,诡娘大人',
    '小烨子,梦游者,苏曦曦,小杰,筱筱,王嘉伦,伦昊然,张亦宸,元气江江,小泷,林金煌,冷沫,余音兔,诗人涵,慕白',
    '小烨子,苏曦曦,小杰,王嘉伦,伦昊然,张亦宸,张灼,诗梦乐.Music.,元气江江,小泷,潮汕皮皮西,梦辰1901 ,林金煌',
    '玉声泩/南曼玉/渔静儿/香菇年/狐狸酱大魔王/李乌兰',
    '田_铮&喜马拉雅', '皇家猫C&喜马拉雅', '洛天依',
    '洛天依,养羊的小蛋黄,火子头,砚笙P,PainKillerXXX,三水暗涌,玄翎P,终幕以后',
    '洛天依,养羊的小蛋黄,终幕以后', '洛天依,玄翎P,终幕以后,养羊的小蛋黄,砚笙P',
    '洛天依,三水暗涌,养羊的小蛋黄,玄翎P,终幕以后', 'Elham Mamat', '漂移的人（Drifting Man）',
    '林依染', 'Fidelia', '砚笙P,养羊的小蛋黄,玄翎P,终幕以后,倾予P,洛天依',
    '林中意,治疗音乐,睡觉轻音乐,睡前音乐盒,养生音乐盒', '睡前音乐盒,林中意,治疗音乐,睡觉轻音乐,养生音乐盒',
    '赞诗', '贊詩', '蟋蟀709', '温香＆三毛', '不乐', '穗穗',
    '穗穗, THEONE', '穗穗, SWEETCOKE027', 'Y$吟升, 穗穗', '穗穗, ALLLPECA', '穗穗, 发发FF',
    '穗穗, LuckY_X范瑞兴', '穗穗゛', '项小景（朗相景）', '汗亮', '黄汉亮', '金保亨',
    '배치기&金保亨', '养生音乐盒', '南征北战NZBZ', '南征北战NZBZ&米线', '五月天',
    '天津市华夏未来少儿艺术团&仔依旺',
    # 茶艾南(佤族/阿卡题材音乐人)
    '茶艾南&紫谷', '茶艾南&杨浩', '茶艾南&陈志和', '尼成NICHENG&肖联祁 MIKEA&茶艾南',
    '茶艾南&鈴木慶一', 'Mikea肖联祁&茶艾南&艾洛-佤', '肖联祁 Mikea&茶艾南', '劳迈&茶艾南',
    '茶艾南, 妮森Nisen', '罗梦雪, 茶艾南', 'Yang Sai, 茶艾南', '茶艾南, 安格拉Angola',
    '茶艾南,安格拉Angola,王峰,张晓伟,耿马歌舞团', '茶艾南&安格拉Angola&王峰疯子&张晓伟&耿马歌舞团',
    '紫谷, 茶艾南',
}
# 歌手名含这些子串的一律删除(有声书平台账号等)
JUNK_SINGER_SUBSTR = ['喜马拉雅']

# 傣文/泰文/缅文/老挝文等字符
TAI_SCRIPT_RE = re.compile(r'[\u0e00-\u0e7f\u1000-\u109f\u0780-\u07bf\u1a20-\u1aaf]')


def dai_reason(t) -> str:
    """返回移出原因; 空字符串表示保留。"""
    name = str(t.get('song_name') or '').strip()
    album = str(t.get('album') or '').strip()
    singer = str(t.get('singers') or '').strip()
    full = ' '.join([name, album, singer])

    # 1) 人工精确删除
    if name in REMOVE_TITLES or (singer, name) in REMOVE_TRACKS:
        return '人工删除(非傣族题材)'
    # 2) 视频源/有声书
    if BV_RE.search(album) or BV_RE.search(name):
        return '视频/直播源'
    if EP_RE.search(album) or EP_RE.search(name):
        return '有声书/评书/连载'
    # 3) 混音噪声(即使带傣族信号也删)
    mix = name + ' ' + album
    for k in JUNK_GENRE:
        if k in mix:
            return 'DJ/喊麦/混音(命中:%s)' % k
    # 4) 明确傣族信号
    if '傣' in full or TAI_SCRIPT_RE.search(full):
        return ''
    # 5) 傣族经典曲目名
    if any(k in name for k in DAI_CLASSICS):
        return ''
    # 6) 傣族专辑名
    if any(k in album for k in DAI_ALBUMS):
        return ''
    # 7) 已核实的垃圾歌手
    if singer in JUNK_SINGERS or any(k in singer for k in JUNK_SINGER_SUBSTR):
        return '非傣族歌手:%s' % singer
    # 8) 非音乐内容
    for k in JUNK_CONTENT:
        if k in mix:
            return '非音乐内容(命中:%s)' % k
    # 9) 其他民族标记
    low = full.lower()
    for k in NON_DAI_TOKENS:
        if k.lower() in low:
            return '非傣族(命中:%s)' % k
    # 10) 默认保留(傣族库存疑项从宽)
    return ''


def is_dai_track(t) -> bool:
    """返回 True 表示保留(傣族歌曲)。"""
    return dai_reason(t) == ''


# ---------------------------------------------------------------- 曲库

class Library:
    def __init__(self):
        self.lock = threading.RLock()
        self.path = None
        self.meta = {}
        self.tracks = []          # 原始 track 列表(含 _song)
        self.idx = []             # 下发前端的轻量索引
        self.singers = []         # [{name,count,cover}]
        self.albums = []
        self.sources = []
        self._by_singer = {}
        self.load()

    # -- 载入 ------------------------------------------------------
    def load(self):
        p = resolve_library_path()
        t0 = time.time()
        with io.open(p, encoding='utf-8') as f:
            d = json.load(f)
        raw = d.get('tracks') or []
        self.path = p

        # ---- 傣族筛选: 仅保留傣族歌曲, 移除其他民族/人工指定曲目 ----
        kept, removed = [], []
        for t in raw:
            r = dai_reason(t)
            if r:
                removed.append((t, r))
            else:
                kept.append(t)
        if removed:
            raw = kept
            self._write_dai_removed(removed, p)
            print('[dai] 已筛选傣族歌曲, 移除 %d 首, 保留 %d 首' % (len(removed), len(raw)), flush=True)

        self.meta = {
            'name': d.get('name') or '傣族 · 民族音乐',
            'group': d.get('group') or '傣族',
            'key': d.get('key') or 'e16',
            'cover': d.get('cover') or '',
            'count': len(raw),
            'kws': d.get('kws') or [],
            'built_at': d.get('built_at'),
            'loaded_at': time.time(),
            'load_seconds': round(time.time() - t0, 2),
            'data_file': str(p),
        }
        self.tracks = raw
        self._build_index()
        self._build_aggs()

    def _build_index(self):
        idx, singers, albums, sources = [], {}, {}, {}
        for i, t in enumerate(self.tracks):
            s = t.get('_song') or {}
            name = (t.get('song_name') or s.get('song_name') or '').strip()
            singer = (t.get('singers') or s.get('singers') or '').strip() or '未知歌手'
            album = (t.get('album') or s.get('album') or '').strip()
            cov = (t.get('cover_url') or s.get('cover_url') or '').strip()
            if not cov or cov.lower() == 'none':
                cov = ''
            dur = t.get('duration_s') or s.get('duration_s') or 0
            try:
                dur = int(float(dur or 0))
            except (TypeError, ValueError):
                dur = 0
            if dur > 4 * 3600:
                dur = 0
            idx.append({
                'i': i,
                'n': name,
                's': singer,
                'a': album,
                'd': dur,
                'c': cov,
                'o': (t.get('source_cn') or t.get('source') or '').strip(),
                'x': (t.get('ext') or s.get('ext') or '').upper(),
                'l': 1 if (t.get('lyric') or s.get('lyric')) else 0,
            })
            if album and album.upper() != 'NULL':
                e = albums.setdefault(album, {'name': album, 'count': 0, 'cover': '', 'singer': ''})
                e['count'] += 1
                if not e['cover'] and cov:
                    e['cover'] = cov
                if not e['singer']:
                    e['singer'] = singer
            for one in re.split(r'[、,，/&;；]+', singer):
                one = one.strip()
                if not one:
                    continue
                e = singers.setdefault(one, {'name': one, 'count': 0, 'cover': ''})
                e['count'] += 1
                if not e['cover'] and cov:
                    e['cover'] = cov
            sc = (t.get('source_cn') or t.get('source') or '其他').strip()
            sources[sc] = sources.get(sc, 0) + 1
        self.idx = idx
        self.singers = sorted(singers.values(), key=lambda x: (-x['count'], x['name']))
        self.albums = sorted(albums.values(), key=lambda x: (-x['count'], x['name']))
        self.sources = sorted(({'name': k, 'count': v} for k, v in sources.items()),
                              key=lambda x: -x['count'])
        self._by_singer = {s['name']: s for s in self.singers}

    def _build_aggs(self):
        pass

    def _write_dai_removed(self, removed, src_path):
        """把被移出的曲目写入报告, 便于审计(已存在则跳过)。

        removed: [(track, reason), ...]
        """
        try:
            HERE = Path(__file__).resolve().parent
            rep = HERE / 'dai_only_removed.json'
            if rep.is_file():
                return
            out = {
                'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'source': str(src_path),
                'count': len(removed),
                'tracks': [{
                    'reason': r,
                    'song_name': t.get('song_name') or '',
                    'singers': t.get('singers') or '',
                    'album': t.get('album') or '',
                    'source': t.get('source_cn') or t.get('source') or '',
                } for t, r in removed],
            }
            with io.open(rep, 'w', encoding='utf-8') as f:
                json.dump(out, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    # -- 查询 ------------------------------------------------------
    def get(self, i):
        with self.lock:
            if 0 <= i < len(self.tracks):
                return self.tracks[i]
        return None

    def song_url(self, i):
        t = self.get(i)
        if not t:
            return None
        s = t.get('_song') or {}
        u = (s.get('download_url') or '').strip()
        return u if u.startswith('http') else None

    def song_identifier(self, i):
        t = self.get(i)
        if not t:
            return ''
        s = t.get('_song') or {}
        return str(s.get('identifier') or '').strip()

    def song_source(self, i):
        t = self.get(i)
        if not t:
            return ''
        s = t.get('_song') or {}
        return str(s.get('source') or '').strip()

    def lyric(self, i):
        t = self.get(i)
        if not t:
            return ''
        s = t.get('_song') or {}
        lrc = s.get('lyric')
        if isinstance(lrc, str) and lrc.strip() and lrc.strip().upper() != 'NULL':
            return lrc
        return ''

    def search(self, kw, limit=60):
        kw = (kw or '').strip().lower()
        if not kw:
            return []
        out, seen = [], set()
        for r in self.idx:
            if kw in r['n'].lower() or kw in r['s'].lower() or kw in r['a'].lower():
                if r['i'] in seen:
                    continue
                seen.add(r['i'])
                out.append(r['i'])
                if len(out) >= limit:
                    break
        return out

    def indices_by_singer(self, name):
        return [r['i'] for r in self.idx if r['s'] == name]

    def indices_by_album(self, name):
        return [r['i'] for r in self.idx if r['a'] == name]

    def indices_by_source(self, name):
        return [r['i'] for r in self.idx if r['o'] == name]

    def hot(self, n=30):
        """热门歌曲: 按歌手热度加权随机, 保证每次会话稳定。"""
        top = {s['name'] for s in self.singers[:12]}
        pool = [r['i'] for r in self.idx if r['s'] in top]
        return pool[:n] if pool else [r['i'] for r in self.idx[:n]]


# ---------------------------------------------------------------- 用户状态

DEFAULT_STATE = {
    'v': 1,
    'fav': [],            # 收藏的曲目 index
    'playlists': [],      # [{id,name,cover,ids:[...],created}]
    'recent': [],         # 最近播放 index(倒序)
    'settings': {'volume': 0.8, 'mode': 'list', 'quality': 'auto', 'skin': 'peacock'},
}


class State:
    def __init__(self):
        self.lock = threading.RLock()
        self.path = data_dir() / 'state.json'
        self.data = json.loads(json.dumps(DEFAULT_STATE))
        self.load()

    def load(self):
        try:
            if self.path.is_file():
                with io.open(self.path, encoding='utf-8') as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    for k, v in DEFAULT_STATE.items():
                        self.data[k] = d.get(k, v)
                    # 补齐 settings 里新增的键(如旧版本没有 skin)
                    if isinstance(self.data.get('settings'), dict):
                        for k, v in DEFAULT_STATE['settings'].items():
                            self.data['settings'].setdefault(k, v)
        except Exception:
            pass

    def save(self):
        with self.lock:
            tmp = self.path.with_suffix('.tmp')
            with io.open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)

    def push_recent(self, i):
        with self.lock:
            r = [x for x in self.data['recent'] if x != i]
            r.insert(0, i)
            self.data['recent'] = r[:300]
        self.save()
