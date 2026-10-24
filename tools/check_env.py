import importlib.util
import sys

print("python", sys.version.split()[0])
for m in [
    "numpy", "scipy", "sklearn", "pandas", "jieba", "gensim", "torch",
    "transformers", "sentence_transformers", "hanlp", "pkuseg", "networkx",
]:
    spec = importlib.util.find_spec(m)
    print(f"{m:22s}", "OK" if spec else "MISSING")
