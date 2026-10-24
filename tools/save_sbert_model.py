"""save_sbert_model.py — 把 bge-small-zh-v1.5 模型本体保存到 data/models/sbert_model/（离线可用）"""
import os
from sentence_transformers import SentenceTransformer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "models", "sbert_model")
os.makedirs(OUT, exist_ok=True)
m = SentenceTransformer("BAAI/bge-small-zh-v1.5", device="cpu")
m.save(OUT)
print("saved:", OUT)
# 冒烟测试：本地加载
m2 = SentenceTransformer(OUT, device="cpu")
v = m2.encode(["测试句子"], normalize_embeddings=True)
print("local reload ok, dim =", v.shape[1])
