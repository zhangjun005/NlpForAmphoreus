"""make_portraits.py — 下载/裁切角色立绘小头像（frontend/public/materials/<slug>-portrait.png）

背景：角色卡左侧的小头像需要 160×188、白底的 PNG；前 8 位角色已有素材，缺
阿格莱雅 / 赛飞儿 / 风堇 / 开拓者 / 三月七 / 丹恒。

来源：StarRailRes（https://github.com/Mar-7th/StarRailRes）的 icon/character/<角色ID>.png
  —— 社区整理的官方素材仓库，角色 ID 来自 index_min/cn/characters.json。
  阿格莱雅=1402、赛飞儿=1406、风堇=1409、三月七=1001、丹恒=1002、开拓者=8007（记忆命途）。
用法：conda run -n nlpLesson python tools/make_portraits.py
输出：frontend/public/materials/*.png（该目录在 frontend/.gitignore 里，属本机素材，不入库）
"""
import io
import os
import urllib.request

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "frontend", "public", "materials")
os.makedirs(OUT, exist_ok=True)

JOBS = [
    ("a-ge-lai-ya", 1402, "阿格莱雅"),
    ("sai-fei-er", 1406, "赛飞儿"),
    ("feng-jin", 1409, "风堇"),
    ("san-yue-qi", 1001, "三月七"),
    ("dan-heng", 1002, "丹恒"),
    ("kai-tuo-zhe", 8007, "开拓者"),
]
UA = {"User-Agent": "dsh"}


def main():
    for slug, cid, name in JOBS:
        url = "https://raw.githubusercontent.com/Mar-7th/StarRailRes/master/icon/character/%d.png" % cid
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()
        im = Image.open(io.BytesIO(raw))
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
            bg.alpha_composite(im)
            im = bg.convert("RGB")
        else:
            im = im.convert("RGB")
        w, h = im.size
        crop_w = int(round(h * 160 / 188))
        if crop_w > w:
            im = im.crop((0, 0, w, int(round(w * 188 / 160))))
        else:
            x = (w - crop_w) // 2
            im = im.crop((x, 0, x + crop_w, h))
        im = im.resize((160, 188), Image.LANCZOS)
        out = os.path.join(OUT, slug + "-portrait.png")
        im.save(out, "PNG", optimize=True)
        print(name, cid, "->", out, os.path.getsize(out))


if __name__ == "__main__":
    main()
