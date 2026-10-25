/** screen-packs-v3.js — 数据包改为 6 章版（主题合并） */
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const j = {
  note: '前端章节数据包（6 章：0 梗概 + 1 数据/表示/模型/读图 + 2 承受命定的人 + 3 改写命定的人 + 4 对偶与旁观 + 5 收束）。每项含：结论句标题、版面方向、数据文件、关键数字、能/不能说明。',
  chapters: [
    {
      id: 'ch01',
      title: '从剧情到数据：表示、模型与读图',
      layout: 'left_text_right_figure',
      merged_from: ['原第1章 两种表示', '原第2章 我们建了什么', '原第3章 图怎么读+A/B1/B2'],
      figures: ['f1_level_scores.png', 'f14_mirror_pair_O10_O11.png', 'f15_retrieval_v3.png'],
      data_files: ['docs/report/figures-index.md', 'data/models/manifest.json', 'data/models/manifest_sbert.json', 'data/plot_data/f1_level_scores.csv'],
      key_numbers: {
        representations: ['词频加权（TF-IDF）', '语义向量（句向量，bge-small-zh-v1.5，512 维）', '余弦相似度（比较方式）'],
        fitted: { tfidf_vocab_dim: 11737, lsa_dim: 100, similarity_matrices: '预计算' },
        pretrained_not_trained: 'bge-small-zh-v1.5（只推理）',
        not_models: '检测器 A/B1/B2 是规则+特征；74 条标注仅评测',
        detectors: { A: '词面+局部情绪', B1: 'A+叙事结构特征', B2: '短步骤修复版（弃用）' },
        axes: {
          f1: 'x=人工等级 0–3；y=标准化分数（0=平均）',
          f6: 'x=36 刀景；y=最好名次（A 13/35、B1 25/35）',
          f12: 'x=版本；y=次数', f13: 'x=全局步序；y=余弦相似度',
          f14: 'x=全局步序；y=余弦相似度', f15: 'x=方法；y=MRR（越高越好）',
          f7_f8: 'x=版本；y=台词/形态/称呼/分数',
        },
      },
      can: '每条曲线可按“词表→向量→余弦”复算；两种表示测不同层面',
      cannot: '相似度高 ≠ 含义深；检测器只测语言变化强度',
    },
    {
      id: 'ch02',
      title: '承受命定的人：沉默、递刀与追认',
      layout: 'left_figure_right_text',
      merged_from: ['原第4章 白厄', '原第8章 万敌', '原第11章 那刻夏'],
      characters: ['白厄', '万敌', '那刻夏'],
      figures: ['f7_bai_trajectory.png'],
      data_files: ['data/plot_data/f7_bai_trajectory.csv', 'data/config/character-trajectory-all.json', 'data/config/oracle-fulfillment.v2.json'],
      key_numbers: {
        bai: { lines: 2550, steps: 202, jiyang: 3, o09_own_citation: '#16719（交出）', v35_lines: 0, v34_split: { 白厄: 425, 卡厄斯兰那: 224, 心中的英雄: 49, 盗火行者: 8, 幼年: 4 } },
        wandi: { lines: 768, steps: 76, weakness: '#7211', deaths: ['#15174 主线', '#17283/#17294 记忆线'] },
        nakesha: { lines: 696, steps: 65, fulfillment_seg: 269, oracle_seg: 315, gap: 46, retro_quote: '#11588' },
      },
      can: '命定可被主动交出，也可被事后追认',
      cannot: '不能证明命运不存在；O06 是单条个案',
    },
    {
      id: 'ch03',
      title: '改写命定的人：讲述、读反与提炼',
      layout: 'left_text_right_figure',
      merged_from: ['原第5章 昔涟', '原第10章 阿格莱雅×赛飞儿中的遐蝶部分（新增）', '原第9章 缇宝'],
      characters: ['昔涟', '遐蝶', '缇宝'],
      figures: ['f8_xi_trajectory.png', 'f13_crystal_flower_semantic.png'],
      data_files: ['data/plot_data/f8_xi_trajectory.csv', 'data/plot_data/oracle_sim__昔涟.csv', 'data/corpus/oracles.jsonl', 'data/config/oracle-citation-coding.json'],
      key_numbers: {
        xi: { lines: 2393, steps: 222, crystal_rewrites: 2, mingtianjian: '1/23（#24598）', v37_centroid: 0.6151 },
        xiadie: { o04_rewrite: '#10091–#10092 → #11467–#11469', confirmation: '#21860–#21861', media_shift: '#1323–#1337 → #10806 → #11486' },
        tiblio: { o02_sources: ['#7939 雅努斯', '#7744 欧洛尼斯'], distilled: '#8049', mingtianjian_series: '13/23', first_occurrence: '#5259（客套）' },
      },
      can: '命定可被讲述、读反、提炼；"原文"本身可加工',
      cannot: '相似度高点≠更懂命定；不能断定缇宝是作者',
    },
    {
      id: 'ch04',
      title: '对偶与旁观：交换、长线与外来者',
      layout: 'left_figure_right_text',
      merged_from: ['原第6章 海瑟音×刻律德菈', '原第10章 阿格莱雅×赛飞儿', '原第7章 列车组'],
      characters: ['海瑟音', '刻律德菈', '阿格莱雅', '赛飞儿', '开拓者', '三月七', '丹恒'],
      figures: ['f14_mirror_pair_O10_O11.png', 'f10_coverage.png'],
      data_files: ['data/plot_data/oracle_sim__阿格莱雅.csv', 'data/plot_data/oracle_sim__赛飞儿.csv', 'data/config/oracle-citation-coding.json', 'data/config/character-trajectory-all.json'],
      key_numbers: {
        mirror: { kelevdela_citations: 0, o11_occurrence: '#20228（海瑟音代念）', o10_occurrence: '#20229', death: '#20339–#20340', conquest_fail: '#20353', inheritance: '#20261→#20322→#20354' },
        long_lines: { aglaea: 942, saifeier: 649, aglaea_chain: '#7458 → #14241–#14242 → #16615', eternal_daylight_edit: '#14400→#14570', coin_chain: '#10329–#10342→#14558→#14577' },
        train_group: { trailblazer: 3058, option_ratio: '79.5%', real_dialogue: 626, march7th: 677, danheng: 1541, danfeng: 89, earth_3_6: 588 },
      },
      can: '归属由谁引用/兑现/交出决定；数据量应扣选项与空窗',
      cannot: '插叙造成假峰，不可当剧情高潮；列车组不可与黄金裔横向比',
    },
    {
      id: 'ch05',
      title: '收束：13 条兑现、明天见、水晶花',
      layout: 'left_figure_right_text',
      merged_from: ['原第12章 收束'],
      figures: ['f4_citation_stage.png', 'f12_mingtian_timeline.png', 'f13_crystal_flower_semantic.png', 'f15_retrieval_v3.png'],
      data_files: ['data/config/key-events.json', 'data/config/oracle-fulfillment.v2.json', 'data/reports/l3/'],
      key_numbers: {
        fulfillment_types: { literal: 8, reversal: 2, misalignment: 1, retroactive: 1, dual_line: 1, two_segment: 1 },
        mingtianjian_unique: 23, closure_3_7: ['#25271', '#25778', '#25779', '#25781'],
        thirteen_heroes: '11 黄金裔 + 三月七 + 丹恒（#26119–#26122 vs #26176）',
        retrieval_v3: { evaluable: '7/13', best_mrr: 0.132 },
      },
      can: '命定从被写死到被改写/被收下的完整轨迹',
      cannot: '不能把语言变化当读者感受；不能把检索排名当剧情重要性',
    },
  ],
};
fs.writeFileSync(path.join(ROOT, 'docs/前端-章节数据包.json'), JSON.stringify(j, null, 2), 'utf8');
console.log('章节数 =', j.chapters.length);
