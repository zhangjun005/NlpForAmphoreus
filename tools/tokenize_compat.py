"""tokenize_compat.py — 与 data/models 中向量器 pickle 兼容的分词函数。

export_artifacts.py 用 analyzer=tokenize（定义在 __main__）拟合 TF-IDF，pickle 里记录的是
`__main__.tokenize`。任何脚本在 joblib.load 之前 import 本模块并把 tokenize 注入 __main__，
即可正常反序列化。保持与 export_artifacts.py 中的逻辑一致。
"""
import re

STOP = set("""
的 了 是 在 我 你 他 她 它 我们 你们 他们 这 那 这个 那个 一个 一种 什么 怎么 为什么 不 也 都 就 而 与 和 或
但 却 又 很 更 最 非常 已经 还是 因为 所以 如果 虽然 但是 然后 可以 没有 不是 自己 这样 那样 一些 这些 那些
啊 吧 呢 吗 呀 哦 唉 嗯 唔 诶 哈 呵 之 其 者 也 矣 焉 哉
""".split())
KEEP_SINGLE = set("汝 吾 尔 她 他 我 你 花 海 火 光 梦 死 生 爱 痛 刀 剑 星 月 日 夜 风 雨 雪 冰 雷".split())


def tokenize(text: str):
    import jieba
    toks = []
    for w in jieba.cut(text or ""):
        w = w.strip()
        if not w or w in STOP:
            continue
        if len(w) == 1 and w not in KEEP_SINGLE and not w.isdigit() and not w.isascii():
            continue
        toks.append(w)
    return toks


def install():
    """把 tokenize 注入 __main__，供 joblib.load 反序列化使用。"""
    import __main__
    __main__.tokenize = tokenize
    __main__.STOP = STOP
    __main__.KEEP_SINGLE = KEEP_SINGLE
