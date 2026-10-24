# 最终归档核对结果

> 由 `tools/final_audit.js` 生成

| 检查项 | 结果 | 详情 |
|---|---|---|
| 图数 = 配对 CSV 数 = 配对 meta 数 | ✅ | png=29 csv=29 meta=29 |
| meta 的 data_sha256_16 与 CSV 一致 | ✅ | ok=29 bad=0 |
| figures-index 数据行数 = 图数 | ✅ | index=29 png=29 |
| data/models/manifest.json 文件全部存在 | ✅ | 22/22 |
| data/models/manifest_sbert.json 文件全部存在 | ✅ | 5/5 |
| ids.records 长度 = 26332 | ✅ | records=26332 |
| ids.segments 长度 = 686 | ✅ | segments=686 |
| ids.oracles 长度 = 13 | ✅ | oracles=13 |
| sbert_model 本地存在（离线可用） | ✅ | 1_Pooling,2_Normalize,config.json,config_sentence_transformers.json,model.safetensors,modules.json,README.md,sentence_bert_config.json,tokenizer.json,tokenizer_config.json |
| 角色质心产物存在（14 角色） | ✅ | npz=true chars=14 |
| L3 笔记 14 份 + 归档 14 份 | ✅ | runtime=14 archive=14 |
| 上下文表 ≥14 个角色（含荒笛历史派生） | ✅ | files=15 |
| 报告 7 章草稿 + 合并稿 | ✅ | drafts=7 merged=true |
| git 工作区干净（派生数据除外） | ❌ |  M "data/config/l3-\350\265\233\351\243\236\345\204\277.json" / ?? "AnalysisV2/\346\212\245\345\221\212.md" / ?? "data/config/l3-\346\230\224\346\266\237.json" / ?? "data/config/l3-\347\231\275\345\216\204.json" / ?? "data/config/l3-\347\274\207\345\256\235.json" |

**通过 13/14**