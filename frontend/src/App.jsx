/**
 * App.jsx — 报告页面的全部内容与组件
 *
 * 页面结构：CHAPTERS（章节目录）/ SYNOPSIS（故事梗概）/ CONTENT（每章正文 + 图卡文字）/
 *   CHARACTER_FIGS（角色卡）/ CHAR_GROUPS（每章角色分组；2 人以上自动整行铺开）/
 *   图组件（FigureCard、CharCard、CharNlp、RetrievalTimeline 等）。
 *
 * 资源约定（重要，改图/换数据前先看这里）：
 * - 每张图 docs/report/figures/<name>.png 都有一份「画这张图用的数据」data/plot_data/<name>.csv，
 *   以及 data/plot_data/<name>.meta.json（记录 axes / sources / filters / generator / sha256）；
 *   全量索引见 docs/report/figures-index.md。图 ↔ CSV ↔ meta 三者必须同步更新。
 * - 页面里的 /figures/*.png 不是源文件：构建前 frontend/scripts/sync-assets.mjs 会把
 *   docs/report/figures/ 下用到的图拷进 frontend/public/figures/，public/ 里的文件不要手改。
 * - 角色卡数据 /data/chars/<角色>.json 由 sync-assets.mjs 从
 *   data/plot_data/chars/<角色>_mini.csv（逐出场步骤的相似度 + 事件标记）
 *   和 data/plot_data/oracle_sim__<角色>.csv（task / step_title）合并生成，字段见 useCharacterData。
 * - 角色向量 × 神谕向量的数字：frontend/src/oracleData.js（由 tools/character_oracle_similarity.py 生成）。
 * - 素材图 /materials/*.png 是从官方 wiki 下载的立绘/主视觉，只做装饰；缺图时 onError 会隐藏，不报错。
 */
import { useEffect, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
  usePlotArea, useXAxisScale, useYAxisScale,
} from 'recharts';
import { ORACLES, OWN_ORACLE, CHAR_ORACLE_RANK, CHAR_ORACLE_MATRIX } from './oracleData.js';

const CHAPTERS = [
  { id: 'ch00', num: '0', title: '故事梗概：被循环困住的世界', kicker: '先看故事，再看数据' },
  { id: 'ch01', num: '1', title: '从剧情到数据：表示、模型与读图', kicker: '两种表示：词频加权与语义向量' },
  { id: 'ch02', num: '2', title: '与命定交手的人：沉默、递刀与追认', kicker: '白厄 / 万敌 / 那刻夏' },
  { id: 'ch03', num: '3', title: '改写命定的人：讲述、读反与提炼', kicker: '昔涟 / 遐蝶 / 缇宝' },
  { id: 'ch04', num: '4', title: '对偶、长线与旁观者：交换、引用链与外来视角', kicker: '海瑟音×刻律德菈 / 阿格莱雅×赛飞儿 / 风堇 / 列车组' },
  { id: 'ch05', num: '5', title: '收束：13 条兑现、明天见、角色曲与水晶花', kicker: '告别、明天与收梢' },
];

const CHAPTER_LEADS = {
  ch02: {
    question: '如果人物很少复述神谕，语言曲线还能说明他承受了命定吗？',
    thesis: '这一章把“说出口的神谕”和“做出来的兑现”分开：白厄交出名字，万敌交出弱点，那刻夏则在事后把经历认回神谕。',
  },
  ch03: {
    question: '改写到底是换掉词，还是保住意思后换一种说法？',
    thesis: '这一章比较三种文本加工：昔涟讲述并重写，遐蝶反转解释，缇宝从他人的话里提炼出新的箴言。',
  },
  ch04: {
    question: '两条神谕用词分不开时，归属应该看词，还是看谁引用、谁兑现？',
    thesis: '这一章把四种情况放在一起看：镜像神谕的归属、长线引用链、风堇被他人见证的兑现，以及列车组的外来视角。',
  },
  ch05: {
    question: '语言变化如何回到完整的剧情兑现，而不是停在相似度排名？',
    thesis: '这一章用三个专题回答：一句话（明天见）怎样从客套变成共同体语言、一首角色曲在语言上离谁最近、一段寓言被改写之后哪条相似度线还记得它；最后把三张图的边界说清楚。',
  },
};

const SYNOPSIS = [
  '翁法罗斯是一座被黑潮围困的世界：大地沉入永夜，唯剩圣城奥赫玛在刻法勒的庇佑下亮着最后一点光。十二泰坦早已疯狂，人们把希望押在「逐火之旅」上——由黄金裔接过十二枚火种、完成「再创世」，让破碎的世界重获新生。每位黄金裔生来都背着一句神谕，命定像钉子一样钉在他们身上；可「再创世」本身是一场骗局，世界被锁在一次次重演的循环里。',
  '黄金裔们逐一登场，也逐一退场。万敌亲手终结了悬锋王朝，也把「背后负创而死」的弱点亲手交给了白厄；阿格莱雅以「最后一次沐浴」收场，而她的谢幕是另一场设计好的死；缇宝把「明天见」当作最伟大的预言送给众生；那刻夏把自己炼进「理性」的火种；海瑟音与刻律德菈各执一条词序颠倒的镜像神谕；赛飞儿用一个谎言维系奥赫玛的永昼；遐蝶把「相拥之后便是永恒的离别」读成「拥抱就是爱」；风堇接过「天空」，荒笛把「大地」留给后来者。',
  '来自星穹列车的开拓者、三月七与丹恒，原本只是误入此地的外来客，却在送别一位位黄金裔的路上，变成愿意接过「负世」职责的参与者。真正撑起三千万次轮回的是白厄与昔涟：白厄一次次回到起点，昔涟把「岁月」剪成可以重写的一页，替他把「救世主」的预言写成希望。最终白厄亲手把「救世主」之名交了出去；昔涟则把自己的「收梢」写成「起始」。',
  '故事落到一本叫《如我所书》的书上：它起初只是昔涟童年那副神谕牌册，后来成了记录银河众生记忆的书；被写下的英雄，最终成了自己写书的人。「明天见」也一路改写：从母亲临终的安慰、从遐蝶口中那个「善意的谎言」，变成黄金裔们共同的预言与誓言——结尾没有句点，只有一句「明天见，乘以一千」。',
];

const RETRIEVAL_RESULT_NOTES = [
  ['关键词', 'v1 和对照组最高，是因为候选池还保留直接念出神谕原句的吟诵步，重点词几乎可以原样命中；去掉吟诵步后仍能抓住“骄阳”等显眼词，但 v3 只剩 0.132。'],
  ['TF-IDF-char', '字符片段不依赖分词，对中文的部分复述比较稳；O10 的兑现段排到第 3，说明它保留了少量字面线索。'],
  ['TF-IDF-word', '词级方法更精确，也更依赖分词和完整词面；兑现段一旦换说法，原神谕里的词不再完整出现，v3 降到 0.029。'],
  ['BM25', '它和词级 TF-IDF 都在找词面证据，所以走势接近；长度校正能减轻长步骤偏置，却不能解决“兑现是改写而不是复述”。'],
  ['LSA', '压缩后的主题方向能保留一部分换词关系，因此 O13 这类主题延续仍有信号；但稀有提示词被压平，难以把具体事件排到前面。'],
  ['SBERT', '短神谕句要和包含多句对白、旁白的长步骤比较，许多语境都会得到相近分数，区分度最低；v3 MRR 只有 0.012。'],
];

const CONTENT = {
  ch01: {
    left: 'text',
    intro: [
      {
        tone: 'blue',
        label: '词频加权 · TF-IDF',
        title: '先看一句话用了哪些词',
        body: '它不先猜意思，只统计词面：一个词在这句话里越集中、在全部语料里越少见，权重就越高。这样可以看出两句话有没有复述相同的词，也能看出一句话究竟把哪些词说得更重。',
        limit: '它的边界是“词袋”：知道出现了哪些词，却不保留词序，也不能单独判断说话者真正想表达什么。',
      },
      {
        tone: 'amber',
        label: '语义向量 · 句向量',
        title: '再看整句话是不是在说相近的事',
        body: '模型把整句话压成一个向量，意思接近的句子在向量空间里的方向也更接近。本项目使用 bge-small-zh-v1.5，把每句话表示成 512 维向量。',
        limit: '它能保留换词后的语境相似，但也可能把“听起来像”的泛化表达当成真正的主题重合。',
      },
      {
        tone: 'green',
        label: '一起读',
        title: '两条线回答的是两个不同的问题',
        body: '词频线回答“有没有说到相同的词”，语义线回答“是不是在说相近的事”。两条线一起抬，才是语言层面较强的证据；只有语义线抬高时，要警惕泛化假峰，只有词频线抬高时，要回到原文确认是不是短语复述。',
        limit: '相似度是语言层的测量，不能替代对剧情事件和人物行为的判断。',
      },
    ],
    pieces: [
      '检索那一组图是我们自己的实验设计。先把三个词说清楚：每条问题都有一个人工确认的“目标段”，也就是我们认为检索应该找回的剧情步骤；候选池是参与检索的 686 个剧情步骤；query 是拿一条神谕原文去查。所谓「吟诵步」，就是剧情里角色把神谕原句念出来或复述出来的步骤。',
      'v1 的问题是：13 条神谕里有 12 条的目标段本身就是吟诵步，其中 10 条直接含原句。关键词和 TF-IDF 找到的可能只是“原句出现在哪里”，这相当于开卷考试，不能说明它找到了真正的兑现事件。v2（v2_mask）把 query 里的原句掩掉，只留下关键词与弱提示，用来检查方法是否依赖原文泄漏。',
      'v3 才把目标段换成神谕真正应验的兑现事件段，同时从候选池剔除 25 个含原句的吟诵步（686→661），再加入 SBERT 语义向量。v3_control 使用同一套兑现事件段、但不剔除吟诵步，用来隔离“剔除原句”这一步的影响。代价是 v3 只剩 7 个可评问题（v1/v2 是 13 个），所以不同版本的 MRR 不能直接横比。',
    ],
    setup: '这些表示作用在 26,332 条记录（台词、旁白、选项）上。词频空间有 11,737 个词，LSA/SVD 只做压缩和定位；bge-small-zh-v1.5 是拿来推理的预训练模型，没有在本项目上重新训练。检测器 A/B1/B2 是规则与特征打分，74 条人工标注只用来评测方向，不是训练集。',
    figures: [
      {
        // f1_level_scores.png：箱线图：检测器 A / B1 的分数分布 vs 人工显著等级 0–3（每箱=一个等级的分数分布）；数据 data/plot_data/f1_level_scores.csv（+ .meta.json）；生成 tools/make_figures.py
        src: '/figures/f1_level_scores.png',
        title: 'f1 等级-分数箱线',
        axes: '横轴是人工显著等级（0=可忽略、1=弱、2=中、3=最强），纵轴是检测器的标准化分数（z 分数；完整定义见本图下方）。',
        judge: '箱体随等级单调上移、0 级最低 3 级最高 = 检测器方向与人工一致（好）；各级重叠、没有趋势 = 不可靠（坏）。A 主要看词面和局部情绪；B1 在 A 之上加入语义突变、身份/位置、母题回收和状态变化，所以带有结构变化的高等级步骤更容易被它抬高。两者都是规则+特征打分，不是训练出来的模型；74 条标注只用于评测方向，不能当准确率。',
        conclusion: 'B1 从 0 级 −0.68 升到 3 级 0.70，A 只从 −0.28 到 0.23 → B1 对“有结构变化的显著步骤”更敏感，但箱体重叠仍说明它只能提供方向，不能替代人工判断。',
        extra: '标准化分数 = 把检测器的原始分减均值、再除以标准差得到的 z 分数：0 就是全库平均，这样 A 与 B1 两套打分才能放在同一把尺子上比较。箱线图里：箱子是中间 50% 的范围，箱内横线是中位数，点（离群值）是个别异常步骤；箱子随等级上移说明方向一致，但重叠区域说明它分不等级别。',
      },
      {
        // f15a_retrieval_mrr.png：柱状图：检索实验各方法的 MRR（4 个 variant × 6 种方法）；数据 data/plot_data/f15a_retrieval_mrr.csv（+ .meta.json）；生成 tools/split_panel_figures.py（由 f15 拆分）
        src: '/figures/f15a_retrieval_mrr.png',
        title: '神谕检索：各方法的 MRR',
        axes: '横轴是检索方法（按 variant 分组），纵轴是 MRR（平均倒数排名；完整定义见本图下方）。',
        judge: '0.5 以上才说明常把目标段排进前几名，0.1 以下基本等于没找到。v1 和对照组里关键词分数高，是因为候选池还保留了直接念出神谕原句的吟诵步，关键词几乎可以原样命中；这不是它理解了兑现。它评的是「排序好不好」，不是「相似度算得对不对」。',
        conclusion: '去掉吟诵步、把目标改成兑现事件后，关键词从 0.480 降到 0.132，六种方法全部接近失败；下降本身说明原先的高分主要来自原句泄漏。',
        extra: 'MRR 是 Mean Reciprocal Rank（平均倒数排名）：把正确答案在返回列表里的名次取倒数——第 1 名得 1、第 2 名得 1/2、第 k 名得 1/k——再对所有可评问题取平均；全部排第一是 1，普遍排在很后面就接近 0。可评问题的设定见正文（v3 只有 7 个，样本小，MRR 差别只能看方向）。',
        methodNotes: RETRIEVAL_RESULT_NOTES,
      },
      {
        // f15b_retrieval_recall.png：折线图：v3 六种检索方法的 Recall@k（k=1/5/10/20）；数据 data/plot_data/f15b_retrieval_recall.csv（+ .meta.json）；生成 tools/split_panel_figures.py（由 f15 拆分）
        src: '/figures/f15b_retrieval_recall.png',
        title: '神谕检索：Recall@k',
        axes: '横轴是 k（前 k 名），纵轴是 Recall@k（前 k 条里出现正确答案的比例；完整定义见本图下方）。每条线是一种检索方法。',
        judge: '曲线越早抬到 1 说明目标段越常出现在前面。v3 各方法到 k=20 仍没有稳定抬升：关键词和字符 TF-IDF 只命中 2/7，词级 TF-IDF、BM25、LSA 只命中 1/7，SBERT 甚至 0/7。',
        conclusion: 'Recall@k 与 MRR 同向：v3 的问题不是某个方法稍微调差了，而是短神谕句与长剧情步骤之间存在粒度错位，目标段通常没有被排到前面。',
        extra: 'Recall@k 是命中率：返回的前 k 条结果里出现正确答案的问题比例，k=1 就等于「只允许第一名命中」，k 越大越宽松。它和 MRR 评的都是排序（正确答案排在多前），不评相似度本身。',
      },
    ],
    post: [
      '两个表示要一起用，最干净的证据是两条镜像神谕：O10「汝将长眠于涛声中，于天地境界之海完成征服」（海瑟音）与 O11「汝将于天地境界之海完成征服，长眠于涛声中」（刻律德菈）。两句用词相同、只换语序，所以词频加权给出的两条曲线在 686 步上逐点相等（最大差 0），语义向量也只给微小差异（平均 0.005、最大 0.018）——只看词或只看语义，都分不开这两条命定。（O01–O13 是全篇 13 条神谕的编号，按报告内顺序排列，后文提到某条命定都用这个编号。）',
    ],
    lateFigures: [
  {
          // f14a_mirror_tfidf.png：两条曲线：O10 / O11 的「词频加权」与神谕相似度，686 步逐点重合；数据 data/plot_data/f14a_mirror_tfidf.csv（+ .meta.json）；生成 tools/split_panel_figures.py（由 f14 拆分）
          src: '/figures/f14a_mirror_tfidf.png',
          title: 'O10 / O11 的镜像曲线：词频加权',
          axes: '横轴是全局步序 1–686，纵轴是与神谕的余弦相似度；实线 O10（海瑟音），虚线 O11（刻律德菈）。',
          judge: '词频加权是词袋，语序被完全丢弃——两条命定只换了语序，所以曲线逐点相等，视觉上完全重合。重合对「区分 O10/O11」是坏，对「证明词面与语序无关」是好。',
          conclusion: '686 个点逐点相等（最大差 0）→ 词频加权完全分不开这两条命定。',
        },
        {
          // f14b_mirror_sbert.png：两条曲线：O10 / O11 的「语义向量」相似度，只差 0.018；数据 data/plot_data/f14b_mirror_sbert.csv（+ .meta.json）；生成 tools/split_panel_figures.py（由 f14 拆分）
          src: '/figures/f14b_mirror_sbert.png',
          title: 'O10 / O11 的镜像曲线：语义向量',
          axes: '横轴是全局步序 1–686，纵轴是与神谕的余弦相似度；实线 O10，虚线 O11。',
          judge: '句向量对语序略有感知，所以两条线不再完全重合，但差异极小——平均 0.005、最大 0.018，仍不足以判断谁属于哪句。',
          conclusion: '语义向量只给出 0.018 的微差 → 同样分不开镜像对，归属只能靠引用与兑现的行为事实。',
        },
    ],
  },
  ch02: {
    left: 'figure',
    pieces: [
      '白厄全篇 2,550 条台词、202 个出场步骤，但和他命定 O09 相关的词极少：白厄 2,550 条台词里「骄阳」只出现 3 次（全语料 8 次），O09 唯一一次「本人引用」是在 3.4 把名字交出去——「诚如神谕所示……愿这名号能代我同行」（#16719）。3.4 的「台词峰值」也不是戏份，而是身份分裂：白厄 425 + 卡厄斯兰那 224 + 心中的英雄 49 + 盗火行者 8 + 幼年 4。3.5 他一句台词都没有。从两种表示看：他的词频加权曲线几乎贴地——不是没有情绪，而是他几乎不说 O09 的词（词袋对「没说出口」是盲的）；语义线在他身份分裂、与故乡道别的段落抬高，那是语域相近，不是引用。把全部台词压成质心再比：O09 词频只排第 3（0.032）、语义排第 10（0.612），词频 top1 反而是 O01（0.069）——整体语言习惯并不贴着命定。',
      '万敌的 O03「终有一日，汝将背后负创而死」听起来像被偷袭，但 3.1 他就亲口告诉白厄「记得从背后刺入我的第十节胸椎，那是唯一能杀死我的弱点」（#7211）。兑现出现两次：主线 3.3（#15174）与记忆线 3.4（#17283/#17294）——两种未来形态的白厄各执行一次。两条线在兑现处都抬得不高：行动上的兑现，不要求语言上复述。质心上 O03 词频排第 1（0.059）、语义第 2（0.672）——他的语言确实围着这句转，但真正定归属的是他递刀的动作。',
      '那刻夏的 O06 有一个配置上的「时间倒置」：v2 把兑现事件段标在 3.2|争辩|2（全库第 269 个剧情步骤），比神谕原句 3.2|学者|4（第 315 个）早 46 个步骤；但同一文件的另一个字段又把兑现标回 3.2|学者|4——两个字段自相矛盾。可以确认的文本事实是：瑟希斯念出原句前「至纯粹」已出现两次，神谕一出他当场判定「只是把我过去、现在和未来成就的一切复述了一遍」（#11588）。「追认」是其中一种读法，不是唯一结论。从表示上看：原句出现的那一步，词频线与语义线同时抬——这是「字面复述」的标志；而配置里的「兑现段」比它早 46 步，正好落在两线都平的地方。质心上 O06 词频只排第 8（0.014）、语义排第 3（0.641）——很少复述原句、语义却靠得近，正好对应「事件之后追认」。',
    ],
    figures: [
      {
        // f7a_bai_lines.png：白厄：每版本台词条数（柱）+ 出场步骤数（线）；数据 data/plot_data/f7a_bai_lines.csv（+ .meta.json）；生成 tools/split_trajectory_panels.py（由 f7 拆分）
        src: '/figures/f7a_bai_lines.png',
        title: '白厄：台词量（柱）与出场步骤（线）',
        axes: '横轴是版本 3.0–3.7，柱子是台词条数，折线是出场步骤数。',
        judge: '台词高说明这一版是主场，折线高说明出场的剧情步骤多；3.1 台词 278 条、步骤 24 个，是「在场但不抢戏」的版本。',
        conclusion: '3.0 台词最多（634 条）且步骤最多（56 个），而 3.5 是 0 条 0 步——缺席本身就是信号：这一版白厄一句话都没有，戏份由别人转述。',
      },
      {
        // f7b_bai_forms.png：白厄：每版本的语言形态构成（堆叠柱，本体/卡厄斯兰那/心中的英雄等）；数据 data/plot_data/f7b_bai_forms.csv（+ .meta.json）；生成 tools/split_trajectory_panels.py（由 f7 拆分）
        src: '/figures/f7b_bai_forms.png',
        title: '白厄：语言形态构成（堆叠）',
        axes: '横轴是版本，纵轴是台词条数，按角色的语言形态（form 字段）堆叠。',
        judge: '同一版本里出现多种形态 = 同一个人用不同声音说话；非本体形态越多，身份分裂越强。形态是文本字段计数，不是模型输出。',
        conclusion: '3.4 的 711 条被拆成白厄本体 425、卡厄斯兰那 224、心中的英雄 49、盗火行者 8、幼年 4——身份峰值在这一版，而不是 3.0 的台词峰值。',
      },
      {
        // f7c_bai_address.png：白厄：称呼词在他自己台词里的命中次数（老师/开拓者/伙伴/英雄等）；数据 data/plot_data/f7c_bai_address.csv（+ .meta.json）；生成 tools/split_trajectory_panels.py（由 f7 拆分）
        src: '/figures/f7c_bai_address.png',
        title: '白厄：称呼词命中（自己的台词）',
        axes: '横轴是版本，纵轴是称呼词在白厄自己台词里的命中次数。',
        judge: '「老师」下降、「伙伴 / 英雄」上升 = 关系从师徒转向同伴；这是纯词面统计，和 TF-IDF 那条曲线看的是同一类证据。',
        conclusion: '「老师」在 3.0 命中 40 次后回落，3.3–3.4 出现「伙伴 / 英雄」——称呼的变化点（3.3 起）比台词量的峰值更早。',
      },
      {
        // f7d_bai_detector.png：白厄：所在步骤的检测器 A / B1 平均分 + B1 前 100 命中率；数据 data/plot_data/f7d_bai_detector.csv（+ .meta.json）；生成 tools/split_trajectory_panels.py（由 f7 拆分）
        src: '/figures/f7d_bai_detector.png',
        title: '白厄：所在步骤的检测器分数',
        axes: '横轴是版本，纵轴是所在步骤的检测器平均分（A / B1；检测器是规则+特征打分，不是训练出来的模型），虚线是 B1 前 100 命中率。',
        judge: '分数高只说明语言突变强，不代表戏份或感动；检测器 A/B1 是规则+特征打分，不是训练模型，不能和语义向量混读。',
        conclusion: '3.2 与 3.4 出现抬升、3.5 断崖（无台词），与形态切换点对齐——检测器抓的是语言风格变化，不是剧情高潮。',
      },
    ],
  },
  ch03: {
    left: 'text',
    pieces: [
      '昔涟贯穿 3.0–3.7，2,393 条台词、222 步，语言形态从「迷迷」的断句体走到「讲述者」和「另一位作者」（按设定即她自己）。她最重的一场戏是 3.7 的水晶花寓言：原版（#23888–#23900）里碎片中有一团光「它是『爱』」（#23894–#23896）；昔涟第一次改（#23901–#23913），说「无瑕」意味着封闭、没有心也不懂爱（#23903–#23913）——终局的第二次改写在收束章再讲。三版整体句向量相似度 0.79–0.87，词频加权只有 0.28–0.47：语义被保住、字面被换掉——这正是两种表示的分工：句向量保住意思，词频加权暴露换词。质心上 O13 词频第 2（0.023）、语义第 2（0.636），词频 top1 是 O01（0.050）——她谈命定更像在转述别人的话。',
      '遐蝶的 O04 是 13 条里反转最彻底的一条：判词说「相拥之后，便是永恒的离别」，她先主动认领「那仿佛并非预言，而是我过去的全部写照」（#10091–#10092），兑现时改写「为它写下另一种诠释」（#11467–#11469），3.6 大墓的记忆场景里还补了一句「我还以为缇宁老师的预言出错了呢」（#21860–#21861）。另一条 O05「汝将凋零，令逝者自残余中发芽」属她妹妹玻吕茜亚（双子共有），她与塞纳托斯重逢时说「无人能独力担起生死的天平」「它本就应该由两只手共同举起」（#11069、#11081）——两条神谕合起来才是「死亡」的完整定义。改写（「另一种诠释」）在词频线上是掉下去的，在语义线上还能维持——改写就是「换词不换意」。质心上 O04 词频第 1（0.067）、语义第 4（0.628）——「相拥之后」的词面出现过，整体语义却更接近 O03（0.640）。',
      '缇宝的 O02 来源不是泰坦原话：雅努斯说「灵魂必遭歧路分离，碎作千片化身，如琉璃掷地……」（#7939），缇宝把它提炼成十四字箴言「汝将碎作千片，凋零在他乡的土壤」（#8049）；「提炼」是精读推断，配置里没有这条记录。她提炼的十四字箴言与原句只有部分词重合：词频线中等、语义线较高，正是「提炼」在两种表示上的特征。质心上 O02 词频第 6（0.011）、语义第 11（0.587）：提炼出的箴言在原句词面上几乎不重合。',
    ],
    figures: [
      {
        // f8a_xi_lines.png：昔涟：每版本台词条数（柱）+ 出场步骤数（线）；数据 data/plot_data/f8a_xi_lines.csv（+ .meta.json）；生成 tools/split_trajectory_panels.py（由 f8 拆分）
        src: '/figures/f8a_xi_lines.png',
        title: '昔涟：台词量（柱）与出场步骤（线）',
        axes: '横轴是版本 3.0–3.7，柱子是台词条数，折线是出场步骤数。',
        judge: '台词与步骤同步上涨 = 从片段式出场变成主要叙述者；只看条数会漏掉「她每场说多长」的变化。',
        conclusion: '从 3.0 的 92 条 / 11 步涨到 3.4 之后的高位（3.4 起她开始承担讲述），数量与在场深度一起上升。',
      },
      {
        // f8b_xi_forms.png：昔涟：每版本的语言形态构成（堆叠柱，迷迷/记忆形态/往昔的涟漪等）；数据 data/plot_data/f8b_xi_forms.csv（+ .meta.json）；生成 tools/split_trajectory_panels.py（由 f8 拆分）
        src: '/figures/f8b_xi_forms.png',
        title: '昔涟：语言形态构成（堆叠）',
        axes: '横轴是版本，纵轴是台词条数，按语言形态堆叠。',
        judge: '形态条的切换点越清楚，越能说明语言阶段在变；「迷迷」的断句体与「讲述者」是两套说话方式，形态字段能直接分开。',
        conclusion: '3.0–3.3 几乎全是「迷迷」，3.4 之后切到「记忆形态 / 往昔的涟漪」，3.7 再出现另一套形态——三个切换点都能在图上指出来。',
      },
      {
        // f8c_xi_address.png：昔涟：称呼词在她自己台词里的命中次数；数据 data/plot_data/f8c_xi_address.csv（+ .meta.json）；生成 tools/split_trajectory_panels.py（由 f8 拆分）
        src: '/figures/f8c_xi_address.png',
        title: '昔涟：称呼词命中（自己的台词）',
        axes: '横轴是版本，纵轴是称呼词在昔涟自己台词里的命中次数。',
        judge: '早期多用「迷迷」式自称与短称呼，后期转向对「你 / 开拓者」的直接对话；称呼变化对应她从旁观者走向讲述者。',
        conclusion: '「开拓者」类称呼在 3.4 之后抬升，与形态切换点同相位；词面统计和 TF-IDF 曲线是同一套视角。',
      },
      {
        // f8d_xi_detector.png：昔涟：所在步骤的检测器 A / B1 平均分 + B1 前 100 命中率；数据 data/plot_data/f8d_xi_detector.csv（+ .meta.json）；生成 tools/split_trajectory_panels.py（由 f8 拆分）
        src: '/figures/f8d_xi_detector.png',
        title: '昔涟：所在步骤的检测器分数',
        axes: '横轴是版本，纵轴是所在步骤的检测器平均分（A / B1；检测器是规则+特征打分，不是训练出来的模型），虚线是 B1 前 100 命中率。',
        judge: '分数上升对应语言从短句走向长句讲述，但分数只是语言突变强度，不等于感人程度；A/B1 是规则+特征打分。',
        conclusion: '3.4 之后分数与命中率抬升，与「迷迷 → 讲述者」的形态切换同相位——检测器与形态字段互相印证，而不是互相替代。',
      },
    ],
  },
  ch04: {
    left: 'figure',
    figureIntro: {
      title: '这一组图怎样接上前面的角色分析',
      paragraphs: [
        '前面的角色卡回答“某个人在自己的轨迹上哪里抬头”；这里把视线拉回全篇：f4 追踪神谕从首次出现、他人解释到本人引用和结局宣告的接管过程，f10 检查我们到底把多少角色步骤读到了可以核对的程度。',
        '所以 f4 不是相似度图，不能用它证明某个峰值；f10 也不是检索准确率。两张图分别补上“谁在什么时候接管神谕”和“这份结论覆盖了多少原始剧情”这两个全局问题。',
      ],
    },
    pieces: [
      '海瑟音与刻律德菈：O10 属海瑟音、O11 属刻律德菈，两条话用词相同、只换语序。但引用分布极不对称：刻律德菈本人 0 次引用神谕，O11 全篇唯一一次出现是海瑟音替她念的（#20228）。兑现也交换了：刻律德菈死于「天地境界之海，一汪浅浅的死水」（#20339–#20340），「完成征服」却落空（#20353）；海瑟音献出余生的清醒与自由（#19814）。半句交换的动作是刻律德菈亲手完成的：赠送「天地境界之海」（#20322）、交付「天外的大海」（#20354）。这一组要记住的结论是：归属由「谁引用、谁兑现、把命定交给谁」决定，而不是词语。表示层同样给出证据：词频加权的两条曲线逐点相等（词袋对语序完全盲），语义向量只差 0.018（句向量对语序只略敏感）——所以两种表示都分不开这对镜像，必须靠引用/兑现的行为事实。质心上也一样：两人对 O10/O11 的词频值各自完全相等（0.102 / 0.076），语义差 ≤0.004，海瑟音甚至更接近 O11（0.684 vs 0.680）。',
      '阿格莱雅完成最完整的引用链：「汝将最后一次沐浴……」（#7458）→ 故人之音把「汝」换成「我」（#14241–#14242）→ 结局宣告「我将最后一次沐浴……现在，是时候将其兑现了」（#16615）；她的退场还接在 K06 遗书与白厄「更好的人」悼词（#12683–#12703、#12746–#12781）之后，不是只有金句。赛飞儿的「千年永昼」只是一次时间短语删改（#14400→#14570）；O08 的「分文」就是她的硬币（#10329–#10342），被夺走后她才失速而死（#14558→#14577–#14578）。引用链上的抬升是词频线与语义线一起抬——因为引用保留了原句的词；而「千年永昼」只是一次短语删改，两线变化都不大。质心上阿格莱雅 O01 词频第 1（0.140，全表最高档之一）、语义第 5；赛飞儿 O08 两种表示都第 1（0.065 / 0.659）——词面重合能认出「她确实反复说那句话」，但认不出归属。',
      '列车组：开拓者 3,058 条里 79.5% 是玩家选项，真实对白与短信只有 626 条；三月七 3.1/3.3 零台词（幽灵期）；丹恒 1,541 条含 89 条「丹枫」，3.6 承接大地火种（荒笛 → 丹恒）。所以列车组单列、不与黄金裔比较：他们的主线塑造在翁法罗斯之外。注意他们的曲线不是「自有命定曲线」，而是「与 13 条神谕的最高相似度」（没有自有神谕时的替代口径），别把它读成第 14 条命定。质心上他们没有自有神谕：词频 top1 都是 O01（0.050 / 0.031）、语义 top1 都是 O08（0.676 / 0.669）——这是 hub 句效应，不是「他们像这条命定」。',
      '风堇是 O07「在彩虹桥的尽头，天空之子将缝补晨昏」的持有者：她把「缝补晨昏」解释成医疗行为（#13042），在 3.3 留下天空、降下虹光（#14642–#14643），并由丹恒宣告应验（#14656–#14657）。她的兑现不是自己喊出来的，而是被他人见证、由他人代言的——这也是「兑现」与「本人引用」不同的地方。图上她 3.3 的峰在留天空、降虹光附近；但宣布应验的那句是丹恒说的，所以词频线抬的地方并不等于「她本人引用」的位置。质心上 O07 词频第 1（0.216，全表最高）、语义却排第 12（0.605）：台词里反复出现「天空/彩虹桥/缝补」这类词，语义空间反而被 hub 句吸走——词面高频不等于命定归属。',
    ],
    figures: [
      {
        // f4_citation_stage.png：引用台账：13 条神谕在剧情里的引用阶段分布（原文出现/他人解释/本人引用/结局宣告/改写）；数据 data/plot_data/f4_citation_stage.csv（+ .meta.json）；生成 tools/make_figures.py
        src: '/figures/f4_citation_stage.png',
        title: 'f4 引用台账（对偶与长线）',
        axes: '横轴是剧情顺序，纵轴是引用阶段（原文出现、他人解释、本人引用、结局宣告、改写）。',
        judge: '阶段从「原文出现/他人解释」移到「本人引用/结局宣告」= 接管完成（好）；停在他人/旁白 = 没接管。方法上：这些阶段是人工按引用编码表打的标签，不是模型输出；f4 与相似度曲线不是同一个指标，不能互相印证。',
        conclusion: '本人引用 19/34、结局宣告 8 条，末次引用时本人 8/13——方向对，但只是弱趋势。',
      },
      {
        // f10_coverage.png：条形：每个角色的出场步骤数 vs 被 L3 精读覆盖的步骤数；数据 data/plot_data/f10_coverage.csv（+ .meta.json）；生成 tools/make_figures.py
        src: '/figures/f10_coverage.png',
        title: 'f10 覆盖率图',
        axes: '横轴是角色（A 组 11 + B 组 3），纵轴是出场步骤数与被「精读」覆盖的步骤数。精读指 L3 阶段人工逐条读该角色剧情并写笔记的步骤，不是检索命中，也不是相似度阈值。',
        judge: '差额越大 = 数据多但没被细读（坏，提示补读）；覆盖率特别高 = 重点标注集中（好，但可能带系统性偏好）。方法上：「精读覆盖」是人工 L3 笔记覆盖的步骤数，不是检索命中率，也不是相似度阈值。',
        conclusion: '开拓者 387 步只有 25 步被精读（6.5%），白厄 22/202（10.9%），刻律德菈 32.3% 最高——这正是后来做 14 角色全量精读（L3）的原因。',
      },
    ],
  },
  ch05: {
    left: 'text',
    // 本章结构：兑现总表 → 三个专题（每个专题＝先讲剧情点与数据起伏的正文，紧跟着它对应的那张图）→ 边界。
    // 「专题一」对应 f12_mingtian_timeline.png，「专题二」对应 f17_lyrics_similarity.png，
    // 「专题三」对应 f13_crystal_flower_semantic.png；三张图都放在各自专题正文的下方，不再堆到章末。
    pieces: [
      '13 条神谕的兑现类型是：字面 10、反转 2、错位 1（合计 13）；另外有三个「结构标签」不计入类型：O03 双线、O06 追认、O13 两段。类型是人工读文本判的，相似度只用来找候选段——两者不能互相替代。',
    ],
    topics: [
      {
        id: 'mingtianjian',
        title: '专题一：「明天」与「明天见」：一句话怎样从客套变成共同体语言',
        paragraphs: [
          '「明天见」全篇出现 23 次。起点是 3.0 归还火种仪式的前夜：阿格莱雅说明日同一时分集合、归还尼卡多利的火种（#4208），白厄答「我明白了。那么，明天见。」（#4211）——全篇第一次出现，只是一句日常道别。到 3.1，它先在谧林商人的客套里出现（#5258 商人、#5259 缇宝「嗯，明天见。也祝你生意兴隆。」），随后缇宝在梦里见到亡母莫忒丝，母亲在梦中的告别里说「明天见，我亲爱的缇里西庇俄丝」（#6876）；同一章里遐蝶质疑「那句明天见只是一个善意的谎言」（#8074），缇宝回答「明天见…是世上最伟大的预言」（#8077）。3.7 的告别段收梢，白厄用「明天见，乘以一千。」（#25779）把它交回给所有人。',
          '时间线上 3.1 是最高的柱子（9 次），3.7 只有 5 次，中间 3.2 是 3 次、3.3–3.6 各 1–2 次。只看高度会得出「3.1 最重要、之后母题消退」的错误结论；把每根柱子按说话人拆开就反过来了：3.1 的 9 次以缇宝为主（6 次），但同时混着母亲莫忒丝、遐蝶与商人的不同语气（4 个说话人，分布熵 1.45 bit）；3.7 的 5 次则分给 5 个不同的人（#24548 开拓者、#24598 昔涟、#25271、#25778 缇宝、#25779 白厄；熵 2.32 bit，全篇最分散）。数量在回落，承载者却在扩散——3.1 还是围绕缇宝一个人展开的对话，3.7 是所有人一起说的收梢句。',
          '两个词也要分开看。「明天」108 条（缇宝 32、昔涟 17、白厄 13），「明天见」23 条；把两个词分别当查询去比 14 个角色质心：词频加权下缇宝对两个词都是第一（明天见 0.190、明天 0.190，远高于第二名的 0.035），语义向量下「明天」最像昔涟（0.4925）、「明天见」最像开拓者（0.556），缇宝只排第 4（0.5433）。说得最多的人（缇宝）、想得最多的人（昔涟谈「明天」17 次、只说 1 次「明天见」）、这句话在语义上像的人（开拓者），是三个不同的人——出现次数、语义中心、字面归属不能互相替代。',
          '计数口径：先按 record 匹配「明天见」得 23 条；「明天」原始 110 条，剔除 2 条跨词误报（#1411、#1468「证明天外之界」里的「明天」）后是 108 条。说话人熵 = −Σp·log2p（p 是每个说话人占本版本的比例），只描述分布分散程度，不评价台词好坏；角色质心 = 该角色全部台词的向量平均，相似度高低不是含义强度。',
        ],
        figures: [
          {
            // f12_mingtian_timeline.png：柱状堆叠：每版本「明天见」出现次数（按说话人）；图上直接标了 #4211 / #8077 / #25779 与 3.7 的五人分布；
            // 数据 data/plot_data/f12_mingtian_timeline.csv（+ .meta.json）；生成 tools/export_plot_data.py（make_new_figures）
            src: '/figures/f12_mingtian_timeline.png',
            wide: true,
            title: '「明天见」时间线：按版本 × 说话人的出现次数',
            axes: '横轴是版本 3.0–3.7，纵轴是「明天见」的出现次数；每根柱子按说话人堆叠（颜色对应图例），柱顶数字是总次数，正文里的说话人熵就是在这些柱子的构成上算的。',
            judge: '别只看柱高：3.1 的 9 次里 6 次来自缇宝，另外 3 次是母亲、遐蝶与商人的不同语气；3.7 的 5 次分给 5 个人——说话人越分散，越接近「共同体语言」。这是字符串计数与说话人分布，不是相似度，也不评台词好坏。',
            conclusion: '数量从 3.1 的峰（9）落到 3.7 的 5，但说话人熵从 1.45 升到 2.32：这句话的扩散发生在「谁在说」，而不是「说了几次」。',
            extra: '图上箭头标了四个可回查的落点：#4211（起点，白厄）、#8077（「世上最伟大的预言」，缇宝）、#25779（「乘以一千」，白厄），以及 3.7 那根柱子里五个说话人各 1 次。柱顶数字与 CSV 的 count 列一致，可逐条核对。',
          },
        ],
      },
      {
        id: 'lyrics',
        title: '专题二：角色曲《昔涟》：歌词在语言上离谁最近',
        paragraphs: [
          '角色曲不是外挂材料：24 条歌词记录（#26218–#26241）就在语料里，位于 3.7「落英啊，残芳纷飞留归躅」第 11 步，是旁白唱词。把它们拼成一段 308 字的查询，和全库 26,332 条台词放进同一套向量空间，问的是「这首歌在语言上离谁最近」，而不是「这首歌属于谁」。',
          '先看 14 个角色质心：昔涟 0.586 排第一，但三月七 0.584、开拓者 0.569 紧跟着，最后一名刻律德菈 0.531——14 个人只差 0.055。这叫「同一语域内的相对差」：歌词用的是通用白话情感词（等待、告别、书页、思念），离谁的台词都不远，所以「最像昔涟」成立，但优势很小，不能当成「这就是昔涟的歌」的证据。',
          '把昔涟自己按版本拆开，差距才明显：3.7 是 0.615、3.6 是 0.606、3.4 是 0.596，3.2 只有 0.517。3.7 是她把故事完本、写进《如我所书》的版本（3.6 大墓段已经出现「讲故事就是信息传送」，3.7 是完成态）；3.4 是她对白厄说「在那『记忆』中，你一定会再次遇见我」的版本。也就是说，歌词与她的距离不随戏份走，而是随「告别—记忆—写书」这条语域走。',
          '换成 13 条神谕来比：最像歌词的是 O04「相拥之后便是永恒的离别」（0.484），她自己的 O13 只有 0.416、排第 5（中间还有 O02 0.425、O09 0.419、O11 0.417）。再看最近的台词（已剔除 24 条歌词本身）：#22359 3.6 大墓「我告别这美丽的世界，只为在你的回忆中…重逢」0.681，#25178 与 #25925 在 3.7 两个任务里重复的同一句诗 0.641，#23970 昔涟 3.7 魔女「下次见面时，就轮到我来为你讲述『爱』的故事了♪」0.610。最近的邻居全是告别与重逢，不是命定条文——角色曲更像在唱「死亡与告别」的母题，而不是复述自己的命定；相似度只回答「语言上像谁」，不回答「这首歌在讲什么」。',
          '词频加权同口径下，昔涟 0.120、O04 0.063、O13 0.035——歌词与台词几乎不共享书面词，是语义相近而不是用词相同。这也是同一段文本在两套表示里会给出不同的「最像」的原因：词面看谁用过这批词，语义看谁在说同一类事。',
        ],
        figures: [
          {
            // f17_lyrics_similarity.png：三格横条：(a) 14 个角色质心 (b) 昔涟 8 个版本质心 (c) 13 条神谕，与 24 条歌词的 SBERT 余弦；
            // 数据 data/plot_data/f17_lyrics_similarity.csv（+ .meta.json）；生成 tools/export_plot_data.py（make_new_figures）
            src: '/figures/f17_lyrics_similarity.png',
            wide: true,
            title: '角色曲《昔涟》与 14 个角色、昔涟各版本、13 条神谕的相似度',
            axes: '三格横条：左是 14 个角色质心，中是昔涟 8 个版本质心，右是 13 条神谕；条越长表示与 24 条歌词的语义余弦越高，数值标在条端。',
            judge: '读三件事：昔涟在 14 人里第一（0.586）、3.7 在 8 个版本里第一（0.615）、但 13 条神谕里第一不是她的 O13 而是 O04（0.484 对 0.416，O13 第 5）。前两格与剧情位置一致，第三格提醒「像谁」不等于「属于谁」。',
            conclusion: '角色曲最接近昔涟，也最接近她的 3.7；但它最近的神谕是「相拥之后便是永恒的离别」——这首歌唱的是告别母题。',
            extra: '词频加权同口径：昔涟 0.120、O04 0.063、O13 0.035，说明相似来自语义而不是共同用词；歌词自身的 24 条已从最近邻里剔除，避免自己命中自己。',
          },
        ],
      },
      {
        id: 'crystal',
        title: '专题三：水晶花寓言：改写之后，哪条线还记得它',
        paragraphs: [
          '原版寓言在 3.7 开头的「魔女的孤诣课题」（#23885–#23913），是昔涟讲给德谬歌的故事：小妖精把无瑕的水晶花碰落，花碎了，碎片里出现一团光，叙述者说「而我知道。它是『爱』」（#23894–#23896）。昔涟接手后第一次改写（#23901–#23913），把「无瑕」解释成封闭、既没有心也不懂爱，把跌落解释成「向命运发起抗争，以破碎书写故事的结局」（#23911）；3.7 收梢再写一次（#25226–#25230），光不在花里也不在眼睛里，而在每一片碎片映出的世界。三版两两的句向量相似度是 0.790–0.872，词频加权只有 0.284–0.468——同一个故事，字面被换掉，意义被保住。',
          '把原版当查询去扫 685 个剧情步骤（留一法排掉它自己那一步）。两条线整体相关只有 0.531：语义线全篇在 0.48–0.54 的窄带里（3.0 均值 0.479、3.7 均值 0.518，极差 0.059），词频线全篇只有 0.015–0.031，但 3.7 的均值 0.031 是 3.0 的两倍。换句话说，语义相似度几乎看不出「改写发生在哪」，词频相似度才画出起伏——这正是「改写」在数据上的样子。',
          '最高点在步序 663（3.7「纸页啊，镌留记忆的涟漪」第 11 步，记录 #25204–#25257）：这一段的主体是黄金裔群像的创世诗和昔涟对开拓者的叙述，终局再写水晶花只占其中五句（#25226–#25230），但就在这五句里词频 0.252、语义 0.785 同时到顶——原词回来了。同一张图里还有两个像峰的地方：步序 594（3.6「大墓啊，深藏轮回的秘密」第 24 步，#22327–#22358，讲《如我所书》就是信息传送、昔涟成为养料）语义 0.662、词频只有 0.068；步序 597（3.6「重逢啊，笑泪相拥的约定」第 2 步，三月七与长夜月合一的那场重逢）语义 0.654、词频 0.058。它们都在讲记忆、告别、重逢，但没说到「水晶花、无瑕、爱」这些词，所以只有语义线抬。这就是假峰：语义线抬只说明「在说相近的事」，两线同抬才说明「在说同一件事」。',
          '词频线的第 2 高在步序 684（3.7「落英…」第 11 步，就是角色曲歌词那一段）0.164：歌和寓言共享「书页、记忆、花、告别」这批词——这也解释了专题二里歌词为什么最像 O04。再看归属：三版最像的角色都是昔涟（0.60 / 0.58 / 0.63），但最像的神谕都是 O04（0.52–0.54），不是她自己的 O13（0.46–0.51）。所以「谁在改写」和「改写成什么语言」是两个问题：改写者是昔涟，改写后的语言更接近「相拥之后便是永恒的离别」。',
        ],
        figures: [
          {
            // f13_crystal_flower_semantic.png：上下双栏折线：原版寓言（#23885–#23913）与 685 步的相似度；上 词频加权、下 语义向量；
            // 图上标了真峰（步663）与假峰（步594/597，3.6 大墓/重逢），阴影为 3.6 段；
            // 数据 data/plot_data/f13_crystal_flower_semantic.csv（+ .meta.json）；生成 tools/export_plot_data.py（make_new_figures）
            src: '/figures/f13_crystal_flower_semantic.png',
            wide: true,
            title: '水晶花寓言曲线：原版（#23885–#23913）与 685 步的相似度',
            axes: '横轴是全局步序 1–686（已排除参考段自身那一步）；上图是词频加权余弦、下图是语义向量余弦，黄色阴影是 3.6 段。细线是原始值、粗线是滚动 25 步平均。',
            judge: '先看 3.6 阴影：语义线抬到 0.66、词频线只有 0.06 —— 假峰（换说法讲相近的主题）；再看步序 663：0.252 与 0.785 同时出现 —— 真收回（原词和原意一起回来）。留一法不是修饰：不排掉参考段自己那一步，会出现相似度 1 的假峰。',
            conclusion: '两线相关 0.531；语义线全程窄带（3.0 均值 0.479 → 3.7 均值 0.518），词频线 3.7 均值是 3.0 的两倍（0.031 对 0.015）→ 改写换了词、保住了意思。',
            extra: '判据：语义线高、词频线不动的步骤只能当「主题相近」的候选，不能当「回收原文」；要两线同抬，并且落点能和剧情事件对上（终局再写水晶花 #25226–#25230）。步序 684 的词频第 2 高正好是歌词段，说明歌与寓言共享词面。',
          },
        ],
      },
      {
        id: 'boundary',
        title: '边界：这三张图各自没说明什么',
        paragraphs: [
          '检索实验已经给出了这条边界：把命中标准换成「真正的兑现事件」后，7 个可评问题里最好的 MRR 只有 0.132，六种方法全部接近失败（曲线见第 1 章的 MRR 与 Recall@k 两张图，这里不重复贴图）；标注一致性 κ=0.788 说明标签可靠，但可靠不等于相似度等于含义。',
          '三张专题图也一样：它们能说明「这句话在哪些版本、由谁说出」（时间线）、「歌词在语言上离谁最近」（角色曲）、「哪一步同时抬高了两条线」（寓言曲线），但都不能替我们判断人物为什么这么做。下面这张表是同一类边界的具体例子：把 11 位黄金裔的终局告别词拿去和前面 699 个步骤做词级检索，再逐条人工判断「是否真的回收前文」——相似度高但只共享一个词的，会被判成「否」。',
        ],
        extra: 'farewell',
      },
    ],
  },

};

function flatten(obj, prefix = '') {
  const out = [];
  for (const [k, v] of Object.entries(obj || {})) {
    const key = prefix ? `${prefix}·${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) out.push(...flatten(v, key));
    else if (Array.isArray(v)) out.push([key, v.join('、')]);
    else out.push([key, String(v)]);
  }
  return out;
}

function KeyNumbers({ data }) {
  if (!data) return null;
  const rows = flatten(data.key_numbers).slice(0, 10);
  return (
    <table className="key-table">
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={k}>
            <th>{k}</th>
            <td>{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function parseSimpleCsv(text) {
  const lines = String(text || '').trim().split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return [];
  const headers = lines[0].split(',');
  return lines.slice(1).map((line) => {
    const values = line.split(',');
    return Object.fromEntries(headers.map((h, i) => [h, values[i] || '']));
  });
}

function summarizeRubyPairs(text) {
  const rows = String(text || '').split(/\r?\n/).filter(Boolean).map((line) => {
    try { return JSON.parse(line); } catch { return null; }
  }).filter(Boolean);
  const counts = new Map();
  for (const row of rows) {
    const key = `${row.display}\u0001${row.gloss}`;
    const current = counts.get(key) || { display: row.display, gloss: row.gloss, count: 0 };
    current.count += 1;
    counts.set(key, current);
  }
  const top = [...counts.values()].sort((a, b) => b.count - a.count).slice(0, 8).map((r) => ({
    ...r,
    use: /泰坦|黎明|天空|大地|海洋|伙伴|搭档/.test(`${r.display}${r.gloss}`) ? '进入神谕词表或检索扩展的候选线索' : '作为语料清洗与释义参考',
  }));
  return { total: rows.length, unique: counts.size, pages: new Set(rows.map((r) => r.page)).size, top };
}

// 角色立绘文件名映射：值 = frontend/public/materials/<slug>-portrait.png
// 14 个角色都有图：160×188 头像裁切，白底。
//   来源：StarRailRes（https://github.com/Mar-7th/StarRailRes）的 icon/character/<角色ID>.png
//   新增 6 张来自 StarRailRes 的 icon/character/<角色ID>.png：阿格莱雅 1402 / 赛飞儿 1406 /
//   风堇 1409 / 三月七 1001 / 丹恒 1002 / 开拓者 8007；由 tools/make_portraits.py 白底合成 →
//   居中裁成 160:188 → resize；前 8 张为早期下载素材。
// 组件里仍保留 onError 隐藏，避免素材缺失时出破图。
const PORTRAITS = {
  白厄: 'bai-e', 万敌: 'wan-di', 那刻夏: 'na-ke-xia', 昔涟: 'xi-lian', 遐蝶: 'xia-die',
  缇宝: 'ti-bao', 海瑟音: 'hai-se-yin', 刻律德菈: 'ke-lv-de-la',
  阿格莱雅: 'a-ge-lai-ya', 赛飞儿: 'sai-fei-er', 风堇: 'feng-jin',
  开拓者: 'kai-tuo-zhe', 三月七: 'san-yue-qi', 丹恒: 'dan-heng',
};

const HL = ['水晶花寓言', '明天见', '明天', '镜像神谕', '收梢即起始', '如我所书', '十三位英雄', '千年永昼',
  'O04', 'O06', 'O09', 'O13', '相拥之后', '拥抱就是爱', '三千万次轮回'];

function renderRich(text) {
  const pattern = new RegExp(`(${HL.join('|')})`, 'g');
  const parts = text.split(pattern);
  return parts.map((p, i) => (HL.includes(p) ? <strong className="hl" key={i}>{p}</strong> : <span key={i}>{p}</span>));
}

const METHOD_HL = ['词频加权', 'TF-IDF', '词袋', '语义向量', '句向量', 'bge-small-zh-v1.5', '512 维', '相似度', '泛化假峰', '语言层'];
function renderMethod(text) {
  const pattern = new RegExp(`(${METHOD_HL.join('|')})`, 'g');
  const parts = String(text || '').split(pattern);
  return parts.map((p, i) => (METHOD_HL.includes(p) ? <strong className="method-hl" key={i}>{p}</strong> : <span key={i}>{p}</span>));
}

const NARRATIVE_BREAK = /(?<=[。！？])(?=(?:从两种表示|质心上|兑现出现|两条线|但同一文件|可以确认|从表示上看|而配置|三版|改写|另一条|这也|所以|注意|兑现也交换|半句交换|这一组|表示层|她提炼|另一|最后|因此))/u;
function splitNarrative(text) {
  const value = String(text || '').trim();
  return value ? value.split(NARRATIVE_BREAK).map((p) => p.trim()).filter(Boolean) : [];
}

function FigureCard({ fig }) {
  const cls = fig.wide ? 'figure-card wide' : 'figure-card split';
  return (
    <figure className={cls}>
      <div className="figure-img">
        <img className={fig.wide ? 'wide' : undefined} src={fig.src} alt={fig.title} loading="lazy" />
        {Array.isArray(fig.methodNotes) && (
          <div className="method-result-notes">
            <strong>这次为什么这样</strong>
            {fig.methodNotes.map(([name, text]) => (
              <p key={name}><b>{name}</b>{text}</p>
            ))}
          </div>
        )}
      </div>
      <figcaption>
        <strong>{fig.title}</strong>
        <p>{fig.axes}</p>
        <p>{fig.judge}</p>
        <p>{fig.conclusion}</p>
        {Array.isArray(fig.extra)
          ? fig.extra.map((t, i) => <p className="fig-extra" key={i}>{t}</p>)
          : fig.extra && <p className="fig-extra">{fig.extra}</p>}
      </figcaption>
    </figure>
  );
}

function FigureBlockIntro({ intro }) {
  if (!intro) return null;
  return (
    <div className="figure-block-intro">
      <h3 className="block-title">{intro.title}</h3>
      {(intro.paragraphs || []).map((p, i) => <p key={i}>{renderRich(p)}</p>)}
    </div>
  );
}

// 第 5 章专题块：每个专题 = 小标题 + 正文 + 它对应的那张图。
// 图不再统一堆到章末：专题一（明天见）下面是 f12 时间线，专题二（角色曲）下面是 f17 三格图，
// 专题三（水晶花）下面是 f13 曲线，边界专题下面是告别语义回溯表 + L3 口径问题。
// 布局：正文全宽（可读行长约 80 字符），图用 wide 图卡整行铺开，保证 1:1 显示、图内文字可读。
function CodaTopics({ topics, farewell, openQuestions }) {
  if (!Array.isArray(topics) || !topics.length) return null;
  return (
    <div className="coda-topics">
      {topics.map((t) => (
        <section className="coda-topic" key={t.id}>
          <h3 className="topic-title">{t.title}</h3>
          <div className="topic-body">
            {t.paragraphs.map((p, i) => <p key={i}>{renderRich(p)}</p>)}
          </div>
          {(t.figures || []).length > 0 && (
            <div className="topic-figure">
              {t.figures.map((f) => <FigureCard fig={f} key={f.src} />)}
            </div>
          )}
          {t.extra === 'farewell' && <FarewellEvidence data={farewell} />}
        </section>
      ))}
      <OpenQuestionsLedger data={openQuestions} />
    </div>
  );
}

function FarewellEvidence({ data }) {
  const rows = (data?.queries || []).filter((q) => q.character !== '荒笛');
  if (!rows.length) return null;
  const totals = rows.reduce((acc, q) => {
    for (const k of ['是', '存疑', '否']) acc[k] += Number(q.verdict_counts?.[k] || 0);
    return acc;
  }, { 是: 0, 存疑: 0, 否: 0 });
  return (
    <section className="topic-data-card farewell-card">
      <h3 className="block-title">告别语义回溯：相似不等于前文回收</h3>
      <p>这份数据把 11 位黄金裔的终局告别词，拿去和前面 699 个剧情步骤做词级/字符级检索，再逐条人工判断是否真的回收前文。它补上了“最后一句话是否把整段人物经历收回来”这个问题。</p>
      <div className="farewell-summary"><span><b>{totals.是}</b>确认回收</span><span><b>{totals.存疑}</b>存疑</span><span><b>{totals.否}</b>仅字面相似</span></div>
      <div className="table-scroll">
        <table className="farewell-table">
          <thead><tr><th>角色</th><th>是</th><th>存疑</th><th>否</th><th>最高命中怎么判</th></tr></thead>
          <tbody>{rows.map((q) => <tr key={q.character}><td><strong>{q.character}</strong></td><td>{q.verdict_counts?.是 || 0}</td><td>{q.verdict_counts?.存疑 || 0}</td><td>{q.verdict_counts?.否 || 0}</td><td>{q.top?.[0]?.best_record_id ? `#${q.top[0].best_record_id} ${q.top[0].verdict}：${q.top[0].reason}` : '—'}</td></tr>)}</tbody>
        </table>
      </div>
      <p className="topic-data-note">口径边界：这是人工复核的“是否回收”判断，不是相似度阈值；高相似但只共享一个词的结果也会被判为“否”。</p>
    </section>
  );
}

function CitationLedger({ data }) {
  const rows = data?.summary?.per_oracle || [];
  if (!rows.length) return null;
  const dist = data.summary.stage_distribution || {};
  return (
    <section className="ledger-block citation-ledger">
      <h3 className="block-title">引用台账：13 条神谕怎样被接管</h3>
      <p className="ledger-lede">这是人工逐条编码的 34 次引用（33 条唯一记录；#20228 同时属于 O10/O11），不是模型从相似度曲线推出来的标签。先看阶段分布，再看每条神谕自己的首现、末次引用和兑现位置。</p>
      <div className="ledger-summary">
        {Object.entries(dist).map(([stage, n]) => <span key={stage}><b>{n}</b>{stage}</span>)}
      </div>
      <div className="table-scroll">
        <table className="citation-table">
          <thead><tr><th>神谕</th><th>持有者</th><th>首次出现</th><th>末次引用</th><th>引用次数</th><th>阶段轨迹</th><th>兑现段</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.oracle_id}>
                <td><strong>{r.oracle_id}</strong><br /><span>{r.text}</span></td>
                <td>{r.holder}</td>
                <td><b>#{r.first?.record_id}</b><br />{r.first?.version} · {r.first?.stage}<br /><small>{r.first?.citer_category} · {r.first?.step_title}</small></td>
                <td><b>#{r.last?.record_id}</b><br />{r.last?.version} · {r.last?.stage}<br /><small>{r.last?.citer_category} · {r.last?.step_title}</small></td>
                <td>{r.n_occurrences}</td>
                <td>{(r.stage_sequence || []).map((s) => <span className="stage-chip" key={s}>{s}</span>)}</td>
                <td>{r.fulfillment_segment || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="ledger-note">读法：末次阶段到达“结局宣告”不等于语言自动证明兑现；它只说明文本在兑现位置明确说出了这条命定。O06 只有原文出现，O10/O11 的归属仍需结合镜像行为判断。</p>
    </section>
  );
}

function KeyEventLedger({ data }) {
  const events = data?.events || [];
  const summary = data?.summary;
  if (!events.length) return null;
  return (
    <details className="ledger-block key-event-ledger">
      <summary><span>关键事件台账：30 个“含义发生变化”的节点</span><em>按剧情顺序展开</em></summary>
      <p className="ledger-lede">这张表不是角色台词量，也不是相似度结果；它把刀子场景、神谕兑现和前后意义变化放在同一条剧情链上。每行都保留了证据记录号，方便从前端回到原始语料。</p>
      {summary && <div className="ledger-summary"><span><b>{summary.n_events}</b>个事件</span><span><b>{summary.n_oracles_covered}</b>条神谕被覆盖</span><span><b>{summary.n_knife_scenes_referenced}</b>个高光场景被引用</span></div>}
      <div className="table-scroll">
        <table className="key-event-table">
          <thead><tr><th>编号 / 阶段</th><th>事件与剧情位置</th><th>前后意义</th><th>证据</th><th>关联</th></tr></thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id}>
                <td><strong>{e.id}</strong><br />{e.phase} · {e.version}</td>
                <td>{e.event_name}<br /><small>{e.segment_step_title || e.segment_id}</small></td>
                <td><b>之前：</b>{e.meaning_before}<br /><b>之后：</b>{e.meaning_after}</td>
                <td>#{e.evidence_record_id} · {e.evidence_speaker}<br />“{e.evidence_quote}”</td>
                <td>{(e.related_oracles || []).join('、') || '—'}<br /><small>{(e.knife_scene_ids || []).join('、')}</small></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function CoverageTable({ rows }) {
  if (!rows?.length) return null;
  return (
    <section className="ledger-block coverage-ledger">
      <h3 className="block-title">精读覆盖台账：f10 的柱子具体代表什么</h3>
      <p className="ledger-lede">总步骤是该角色在全库中出现过的剧情步骤；精读步骤是 L3 阶段逐条读过并写笔记的步骤；标注条数是其中留下人工标注的数量。覆盖率低不等于角色不重要，只说明图下方的解释要更谨慎。</p>
      <div className="table-scroll">
        <table className="coverage-table">
          <thead><tr><th>角色</th><th>组别</th><th>总步骤</th><th>L3 精读</th><th>人工标注</th><th>精读覆盖率</th></tr></thead>
          <tbody>{rows.map((r) => <tr key={r.char}><td><strong>{r.char}</strong></td><td>{r.group === 'A' ? '黄金裔' : '列车组'}</td><td>{r.n_steps}</td><td>{r.deep_n}</td><td>{r.annotation_n}</td><td>{(Number(r.deep_rate) * 100).toFixed(1)}%</td></tr>)}</tbody>
        </table>
      </div>
    </section>
  );
}

function BaselineComparison({ data }) {
  const cmp = data?.a_b1_b2;
  if (!cmp) return null;
  const rows = [
    ['A', cmp.A],
    ['B1', cmp.B1],
    ['B2', cmp.B2],
  ].filter(([, r]) => r);
  return (
    <section className="ledger-block baseline-ledger">
      <h3 className="block-title">检测器版本对照：B2 改了什么</h3>
      <p className="ledger-lede">f1 图展示 A 与 B1；B2 只修正短步骤的语义突变计算，长步骤的分数与 B1 完全一致。它不是第四种模型，而是一次口径敏感性检查。</p>
      <div className="table-scroll">
        <table className="baseline-table">
          <thead><tr><th>版本</th><th>评测样本</th><th>与人工等级 Spearman</th><th>显著样本进 Top100</th><th>等级 0 / 3 平均分</th></tr></thead>
          <tbody>{rows.map(([name, r]) => <tr key={name}><td><strong>{name}</strong></td><td>{r.n_samples}</td><td>{Number(r.spearman).toFixed(3)}</td><td>{r.significant_in_top100}</td><td>{Number(r.level_means?.['0']).toFixed(3)} / {Number(r.level_means?.['3']).toFixed(3)}</td></tr>)}</tbody>
        </table>
      </div>
      <p className="ledger-note">B1 的等级区分度最高（Spearman 0.581）；B2 把短步骤的语义距离换成句内相邻距离和半步对比后为 0.541。这个变化说明短步骤的分数对计算口径敏感，不能把一次排名当成稳定的叙事显著性判定。</p>
    </section>
  );
}

function StyleCompareCard({ data }) {
  const overall = data?.overall;
  const meta = data?.meta;
  if (!overall || !meta) return null;
  const labels = {
    literary_rate: '文言虚词',
    modal_rate: '情态词',
    person2_rate: '第二人称',
    abstract_ratio: '抽象名词比例',
  };
  const features = Object.keys(labels);
  const groups = ['G1', 'G2', 'G3'];
  return (
    <section className="ledger-block style-ledger">
      <h3 className="block-title">语言风格对比：神谕的声音为什么不同</h3>
      <p className="ledger-lede">这里不使用 embedding，只比较句子里的可解释特征：G1 是 13 条神谕拆出的 14 句，G2 是按版本抽样的 181 条普通剧情对白，G3 是 34 次引用拆出的 48 句。G3 是“神谕被说出口后的样子”，不是新的神谕集合。</p>
      <div className="style-groups"><span><b>G1</b>神谕原文 · {meta.group_unit_counts?.G1} 句</span><span><b>G2</b>普通剧情句 · {meta.group_unit_counts?.G2} 句</span><span><b>G3</b>神谕引用句 · {meta.group_unit_counts?.G3} 句</span></div>
      <div className="table-scroll">
        <table className="style-table">
          <thead><tr><th>特征（每百字或比例）</th>{groups.map((g) => <th key={g}>{g} 均值</th>)}</tr></thead>
          <tbody>{features.map((key) => <tr key={key}><td>{labels[key]}</td>{groups.map((g) => <td key={g}>{Number(overall.features?.[key]?.[g]?.mean || 0).toFixed(3)}</td>)}</tr>)}</tbody>
        </table>
      </div>
      <p className="style-conclusion">读法：G1 在文言虚词、情态词、第二人称和抽象概念上整体高于普通剧情句；G3 在 13 个特征中有 10 个更接近 G1，说明角色引用神谕时仍保留一部分神谕的语言骨架，但它不是“说得越像就越接近命定”的证明。</p>
      <p className="ledger-note">统计边界：Mann–Whitney U + Cliff's delta，并做 Bonferroni 校正；G1 只有 14 个句子，结论只能作为方向性风格证据。</p>
    </section>
  );
}

function RubyPairsCard({ data }) {
  if (!data) return null;
  return (
    <section className="ledger-block ruby-ledger">
      <h3 className="block-title">注音数据：神谕里的词面和解释不是一回事</h3>
      <p className="ledger-lede">语料里共有 {data.total} 条注音配对，覆盖 {data.pages} 个剧情页面。它们不是额外的台词，也不是模型预测；它们是原始文本给出的“表面词 → 解释”线索，参与神谕词表和部分检索 query 的构建。</p>
      <div className="ruby-summary"><span><b>{data.total}</b>条配对</span><span><b>{data.unique}</b>组唯一映射</span><span><b>{data.pages}</b>个页面</span></div>
      <div className="table-scroll">
        <table className="ruby-table">
          <thead><tr><th>表面词</th><th>注音解释</th><th>出现次数</th><th>它在分析里怎么用</th></tr></thead>
          <tbody>{data.top.map((r) => <tr key={`${r.display}-${r.gloss}`}><td><strong>{r.display}</strong></td><td>{r.gloss}</td><td>{r.count}</td><td>{r.use}</td></tr>)}</tbody>
        </table>
      </div>
      <p className="ledger-note">边界：注音解释只能提供语料中的语义线索，不能替代剧情兑现判断；例如“天空之子”可以帮助检索连接到风堇，但最终仍要回到引用、行动和事件证据。</p>
    </section>
  );
}

function OpenQuestionsLedger({ data }) {
  const items = data?.items || [];
  if (!items.length) return null;
  const open = items.filter((x) => x.status === 'open');
  return (
    <details className="ledger-block open-questions-ledger">
      <summary><span>L3 口径问题：哪些已经解决，哪些仍开放</span><em>{items.length - open.length} 已解决 · {open.length} 开放</em></summary>
      <p className="ledger-lede">这些不是模型报错，而是逐条精读时发现的文本归属、时间线和配置口径问题。已解决项记录采用的判断；开放项必须在讲解中保留不确定性。</p>
      <div className="table-scroll">
        <table className="open-question-table">
          <thead><tr><th>状态</th><th>编号 / 角色</th><th>问题</th><th>当前决定</th></tr></thead>
          <tbody>{items.map((x) => <tr key={x.id} className={x.status === 'open' ? 'is-open' : undefined}><td>{x.status === 'open' ? '开放' : '已解决'}</td><td><strong>{x.id}</strong><br />{x.char}</td><td>{x.issue}</td><td>{x.decision}</td></tr>)}</tbody>
        </table>
      </div>
    </details>
  );
}

const CHARACTER_FIGS = {
  ch02: [
    // 白厄_mini.png：白厄的三联迷你图（台词量/步骤、自身神谕相似度+事件标记、称呼 Top5）；数据 data/plot_data/chars/白厄_mini.csv；生成 tools/make_character_mini_figures.py
    { name: '白厄', img: '/figures/chars/白厄_mini.png', note: '沉默：唯一一次引用就是完整背出 O09 并交出名字；3.4 是身份分裂峰值' },
    // 万敌_mini.png：万敌的三联迷你图（台词量/步骤、自身神谕相似度+事件标记、称呼 Top5）；数据 data/plot_data/chars/万敌_mini.csv；生成 tools/make_character_mini_figures.py
    { name: '万敌', img: '/figures/chars/万敌_mini.png', note: '递刀：3.1 交出弱点，两次兑现各一次' },
    // 那刻夏_mini.png：那刻夏的三联迷你图（台词量/步骤、自身神谕相似度+事件标记、称呼 Top5）；数据 data/plot_data/chars/那刻夏_mini.csv；生成 tools/make_character_mini_figures.py
    { name: '那刻夏', img: '/figures/chars/那刻夏_mini.png', note: '配置把兑现段标得比原句早 46 步（两字段矛盾，追认只是其中一种读法）' },
  ],
  ch03: [
    // 昔涟_mini.png：昔涟的三联迷你图（台词量/步骤、自身神谕相似度+事件标记、称呼 Top5）；数据 data/plot_data/chars/昔涟_mini.csv；生成 tools/make_character_mini_figures.py
    { name: '昔涟', img: '/figures/chars/昔涟_mini.png', note: '讲述/写书：水晶花被改写两次，3.7 峰值' },
    // 遐蝶_mini.png：遐蝶的三联迷你图（台词量/步骤、自身神谕相似度+事件标记、称呼 Top5）；数据 data/plot_data/chars/遐蝶_mini.csv；生成 tools/make_character_mini_figures.py
    { name: '遐蝶', img: '/figures/chars/遐蝶_mini.png', note: '读反：O04 从「永恒离别」改成「拥抱=爱」' },
    // 缇宝_mini.png：缇宝的三联迷你图（台词量/步骤、自身神谕相似度+事件标记、称呼 Top5）；数据 data/plot_data/chars/缇宝_mini.csv；生成 tools/make_character_mini_figures.py
    { name: '缇宝', img: '/figures/chars/缇宝_mini.png', note: '提炼：O02 是她从雅努斯的散文里提炼的箴言' },
  ],
  ch04: [
    // 海瑟音_mini.png：海瑟音的三联迷你图（台词量/步骤、自身神谕相似度+事件标记、称呼 Top5）；数据 data/plot_data/chars/海瑟音_mini.csv；生成 tools/make_character_mini_figures.py
    { name: '海瑟音', img: '/figures/chars/海瑟音_mini.png', note: '镜像对：代念 O11，自己放弃征服、长眠守墓' },
    // 刻律德菈_mini.png：刻律德菈的三联迷你图（台词量/步骤、自身神谕相似度+事件标记、称呼 Top5）；数据 data/plot_data/chars/刻律德菈_mini.csv；生成 tools/make_character_mini_figures.py
    { name: '刻律德菈', img: '/figures/chars/刻律德菈_mini.png', note: '镜像对：0 次引用神谕，把「完成」换到律法上' },
    // 阿格莱雅_mini.png：阿格莱雅的三联迷你图（台词量/步骤、自身神谕相似度+事件标记、称呼 Top5）；数据 data/plot_data/chars/阿格莱雅_mini.csv；生成 tools/make_character_mini_figures.py
    { name: '阿格莱雅', img: '/figures/chars/阿格莱雅_mini.png', note: '全链：汝→我→结局宣告，沐浴母题仅 7 次' },
    // 赛飞儿_mini.png：赛飞儿的三联迷你图（台词量/步骤、自身神谕相似度+事件标记、称呼 Top5）；数据 data/plot_data/chars/赛飞儿_mini.csv；生成 tools/make_character_mini_figures.py
    { name: '赛飞儿', img: '/figures/chars/赛飞儿_mini.png', note: '道具链：千年永昼是短语删改，O08=硬币' },
    // 开拓者_mini.png：开拓者的三联迷你图（台词量/步骤、自身神谕相似度+事件标记、称呼 Top5）；数据 data/plot_data/chars/开拓者_mini.csv；生成 tools/make_character_mini_figures.py
    { name: '开拓者', img: '/figures/chars/开拓者_mini.png', note: '旁观者：3,058 条里 79.5% 是选项' },
    // 三月七_mini.png：三月七的三联迷你图（台词量/步骤、自身神谕相似度+事件标记、称呼 Top5）；数据 data/plot_data/chars/三月七_mini.csv；生成 tools/make_character_mini_figures.py
    { name: '三月七', img: '/figures/chars/三月七_mini.png', note: '旁观者：3.1/3.3 零台词（幽灵期）' },
    // 丹恒_mini.png：丹恒的三联迷你图（台词量/步骤、自身神谕相似度+事件标记、称呼 Top5）；数据 data/plot_data/chars/丹恒_mini.csv；生成 tools/make_character_mini_figures.py
    { name: '丹恒', img: '/figures/chars/丹恒_mini.png', note: '旁观者：1,541 条含 89 条「丹枫」' },
    // 风堇_mini.png：风堇的三联迷你图（台词量/步骤、自身神谕相似度+事件标记、称呼 Top5）；数据 data/plot_data/chars/风堇_mini.csv；生成 tools/make_character_mini_figures.py
    { name: '风堇', img: '/figures/chars/风堇_mini.png', note: '被见证：O07 留天空、降虹光，由丹恒宣告应验' },
  ],
};

const CHARACTER_SPECIALS = {
  昔涟: {
    title: '水晶花寓言：昔涟为什么要改写它',
    paragraphs: [
      '原版寓言（#23885–#23913）不是一段泛泛的童话，而是昔涟把「无瑕」重新解释成「封闭」的现场：她讲给德谬歌的故事里，小妖精把无瑕的水晶花碰落，碎片里出现一团光，叙述者说「而我知道。它是『爱』」；昔涟接手后却把结局改成「无瑕的花既没有心，也不懂爱」，再把「破碎」解释成向命运发起抗争。',
      '因此这里会看到典型的错峰：原句和「碎裂、无瑕、爱」同场时，词频线容易抬高；到了昔涟用自己的话解释「封闭、心、爱、抗争」时，原词被换掉，语义仍然连续，词频却会回落。图上要守住两条边界：留一法已经排除参考段自身那一步，词频峰落在步序 663（3.7 结尾）；3.5 有一段较轻的语义隆起，但最强的「只有语义线抬」出现在 3.6 大墓/重逢段。逐点读法放在第 5 章专题三（那里有整段 685 步的曲线）。',
    ],
    evidence: '原文证据：记忆的花 #23894–#23897；昔涟第一次改写 #23901–#23913；终局再写水晶花 #25226–#25230。',
  },
};

const CHAR_GROUPS = {
  ch02: [[['白厄'], 0], [['万敌'], 1], [['那刻夏'], 2]],
  ch03: [[['昔涟'], 0], [['遐蝶'], 1], [['缇宝'], 2]],
  ch04: [[['海瑟音', '刻律德菈'], 0], [['阿格莱雅', '赛飞儿'], 1], [['开拓者', '三月七', '丹恒'], 2], [['风堇'], 3]],
};

const GROUP_LABELS = {
  ch02: ['白厄：把命定交出去', '万敌：把弱点交出去', '那刻夏：在事后认回命定'],
  ch03: ['昔涟：讲述与重写', '遐蝶：反转解释', '缇宝：从他人话语中提炼'],
  ch04: ['镜像神谕：词语分不开，行为来归属', '长线引用：命定如何被反复接管', '列车组：外来者的旁观与参与', '风堇：被他人见证的兑现'],
};

const EVENT_FLAGS = [
  { key: 'in_oracle_first', name: '神谕文本首现', color: '#2c3e50' },
  { key: 'in_recitation', name: '吟诵', color: '#8e44ad' },
  { key: 'in_fulfillment', name: '兑现', color: '#c0392b' },
  { key: 'in_key_event', name: '关键事件', color: '#2e8b57' },
  { key: 'in_knife', name: '高光场景', color: '#d35400' },
];

// 图上直接标注的关键事件（按优先级各取最早一次，最多 3 条）
const ANNOT_FLAGS = [
  { key: 'in_fulfillment', name: '兑现', color: '#c0392b' },
  { key: 'in_knife', name: '高光场景', color: '#b4551c' },
  { key: 'in_oracle_first', name: '神谕文本首现', color: '#2f3e4e' },
  { key: 'in_recitation', name: '吟诵', color: '#8e44ad' },
];

function oracleLine(name) {
  const ids = OWN_ORACLE[name] || [];
  if (!ids.length) return '无自有神谕（外来视角，取与 13 条神谕的最高相似度）';
  return ids.map((id) => `${id}「${ORACLES[id] ? ORACLES[id].text : ''}」`).join('　');
}

function clip(text, max = 16) {
  const t = String(text || '');
  return t.length > max ? `${t.slice(0, max)}…` : t;
}

// 悬停读数：固定出现在光标下方（allowEscapeViewBox.y），不再盖住图
function CharTip({ active, payload, bar }) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload || {};
  if (bar) {
    return (
      <div className="char-tip">
        <div className="char-tip-h">版本 {p.version}</div>
        <div className="char-tip-b">台词 {p['台词量']} 条</div>
      </div>
    );
  }
  const pick = (k) => {
    const item = payload.find((x) => x.dataKey === k);
    return item && typeof item.value === 'number' ? item.value.toFixed(3) : '—';
  };
  return (
    <div className="char-tip">
      <div className="char-tip-h">{p.version}｜{clip(p.title || p.task)}</div>
      <div className="char-tip-b">第 {p['步序']} 次出场　词频加权 {pick('词频加权')}　语义向量 {pick('语义向量')}</div>
    </div>
  );
}

// 用 recharts 3 的坐标 hook 把数据点换算成像素，画带箭头的标注
function EventCallouts({ marks }) {
  const xScale = useXAxisScale();
  const yScale = useYAxisScale();
  const plot = usePlotArea();
  if (!marks.length || !xScale || !yScale || !plot) return null;
  const left = plot.x;
  const right = plot.x + plot.width;
  const top = plot.y;
  // 卡片很窄时只标最重要的一条，且不写版本号，避免箭头文字被裁掉
  const narrow = plot.width < 320;
  const shown = narrow ? marks.slice(0, 1) : marks;
  const pad = narrow ? 28 : 36;
  return (
    <g className="callouts">
      {shown.map((m, idx) => {
        const cx = xScale(m.step);
        const cy = yScale(m.y);
        if (cx == null || cy == null || Number.isNaN(cx) || Number.isNaN(cy)) return null;
        // 窄卡片只有 1 条标注：统一放到图顶并拉一条指引线，避免文字压在数据上
        const above = narrow ? true : cy - top > 54;
        const rawY = narrow ? top + 11 : (above ? cy - 24 - (idx % 2) * 18 : cy + 30 + (idx % 2) * 16);
        // 别让标签压到数据点：留出顶部 14px 的安全边
        const labelY = Math.max(rawY, top + 14);
        const lx = Math.min(Math.max(cx, left + pad), right - pad);
        const dx = cx - lx;
        const dy = cy - labelY;
        const len = Math.hypot(dx, dy) || 1;
        const ux = dx / len;
        const uy = dy / len;
        const tip = { x: cx - ux * 4, y: cy - uy * 4 };
        const base = { x: tip.x - ux * 7, y: tip.y - uy * 7 };
        const px = -uy * 3.2;
        const py = ux * 3.2;
        return (
          <g key={`m-${m.step}`}>
            <line x1={lx} y1={labelY + (above ? 5 : -10)} x2={base.x} y2={base.y}
              stroke={m.color} strokeWidth={0.9} strokeDasharray="2 2" opacity={0.85} />
            <polygon
              points={`${tip.x},${tip.y} ${base.x + px},${base.y + py} ${base.x - px},${base.y - py}`}
              fill={m.color} />
            <circle cx={cx} cy={cy} r={3.4} fill="#fff" stroke={m.color} strokeWidth={1.6} />
            <text x={lx} y={labelY} textAnchor="middle" fontSize={10.5} fontWeight={700} fill={m.color}
              style={{ paintOrder: 'stroke', stroke: '#ffffff', strokeWidth: 3, strokeLinejoin: 'round' }}>
              {narrow ? m.name : m.label}
            </text>
          </g>
        );
      })}
    </g>
  );
}

// 拉取 /data/chars/<角色>.json：该角色逐「出场步骤」的曲线数据。
// 每行字段：step_index=该角色第 N 次出场；version=版本；task/step_title=这一步属于哪个任务/剧情步骤；
//   tfidf_own=与自有神谕的「词频加权」余弦；sbert_own=「语义向量」余弦；
//   in_oracle_first/in_recitation/in_fulfillment/in_key_event/in_knife=五类事件标记（0/1，按精确 segment_id 打）；
//   version_n_records=该版本该角色台词条数。
// 这些 JSON 是构建前由 frontend/scripts/sync-assets.mjs 生成的，源数据在 data/plot_data/chars/。
function useCharacterData(name) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    let alive = true;
    fetch(`/data/chars/${encodeURIComponent(name)}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => { if (alive) setRows(d); })
      .catch(() => { if (alive) setRows([]); });
    return () => { alive = false; };
  }, [name]);
  return rows;
}

function HighlightEvidence({ name, scenes, compact }) {
  const roleScenes = (scenes || [])
    .filter((s) => s.role === name)
    .sort((a, b) => (b.intensity || 0) - (a.intensity || 0) || (a.scene_order_index || 0) - (b.scene_order_index || 0));
  const scene = roleScenes[0];
  if (!scene) return null;
  const records = (scene.records || [])
    .filter((r) => r && r.text && !['option', 'sms_option'].includes(r.kind))
    .slice(0, compact ? 2 : 4);
  return (
    <div className="highlight-evidence">
      <div className="highlight-head">
        <span>代表高光证据</span>
        <strong>{scene.id} · {scene.title}</strong>
        <em>强度 {scene.intensity}/5</em>
      </div>
      <p className="highlight-why">{scene.why}</p>
      <div className="highlight-lines">
        {records.map((r) => (
          <p key={r.id}><span>#{r.id}</span><b>{r.speaker || '旁白'}</b>{r.text}</p>
        ))}
      </div>
      <p className="highlight-source">证据范围：{scene.ranges?.[0] || scene.segment_ids?.[0] || scene.id}</p>
    </div>
  );
}

function peakRow(rows, key) {
  const usable = (rows || []).filter((r) => Number.isFinite(Number(r[key])));
  if (!usable.length) return null;
  return usable.reduce((best, row) => Number(row[key]) > Number(best[key]) ? row : best, usable[0]);
}

function peakTitle(row) {
  if (!row) return '没有可用数据';
  return `${row.version || '未知版本'} · ${row.step_title || row.task || '未命名步骤'}（第 ${row.step_index} 次出场）`;
}

function peakEvents(row) {
  return row ? EVENT_FLAGS.filter((f) => row[f.key]).map((f) => f.name) : [];
}

function explainPeak(row, kind) {
  if (!row) return '没有可用的峰值数据。';
  const value = Number(row[kind === '词频' ? 'tfidf_own' : 'sbert_own']);
  const events = peakEvents(row);
  const eventText = events.length ? `这一行带有“${events.join('、')}”标记` : '这一行没有神谕首现、吟诵、兑现或高光标记';
  if (kind === '词频') {
    if (row.in_recitation || row.in_oracle_first) return `词频峰值 ${value.toFixed(3)} 出现在${peakTitle(row)}；${eventText}，说明它抬高的主要原因是原句或原句片段进入了这一段。它能证明字面线索存在，不能单独证明剧情在这里完成兑现。`;
    if (row.in_fulfillment) return `词频峰值 ${value.toFixed(3)} 落在${peakTitle(row)}；${eventText}，说明兑现段仍保留了神谕里的部分词面。这里比“直接吟诵”更接近真正的事件证据，但仍要回看台词。`;
    return `词频峰值 ${value.toFixed(3)} 出现在${peakTitle(row)}；${eventText}，所以它目前只能解释为局部词面重合，不能把这个峰直接读成神谕兑现。`;
  }
  if (row.in_fulfillment || row.in_key_event || row.in_knife) return `语义峰值 ${value.toFixed(3)} 出现在${peakTitle(row)}；${eventText}，说明这一段的行动或情境和神谕方向相近。语义峰保留的是“在说相近的事”，不是原句复述。`;
  return `语义峰值 ${value.toFixed(3)} 出现在${peakTitle(row)}；${eventText}，更像语境相近的候选峰。没有剧情标记时，它必须和原文、引用台账一起读，不能单独当作兑现证据。`;
}

function PeakRecords({ evidence }) {
  const records = (evidence?.records || []).slice(0, 2);
  if (!records.length) return null;
  return (
    <div className="peak-records">
      <span>对应片段：{evidence.segment_id || '未对齐'}</span>
      {records.map((r) => <p key={r.id}><b>#{r.id} {r.speaker || '旁白'}</b>：{r.text}</p>)}
    </div>
  );
}

function CurvePeakExplanation({ rows, name, evidence }) {
  if (!rows || !rows.length) return null;
  const tf = peakRow(rows, 'tfidf_own');
  const sb = peakRow(rows, 'sbert_own');
  if (!tf && !sb) return null;
  const tfValue = Number(tf?.tfidf_own || 0);
  const separated = tf && sb && tf.step_index !== sb.step_index;
  const hasOwnOracle = (OWN_ORACLE[name] || []).length > 0;
  return (
    <div className="curve-peak-explanation">
      <strong>这张角色图的峰值怎么读</strong>
      {!hasOwnOracle && <p className="curve-peak-boundary"><b>先说明口径：</b>{name}没有自有神谕，图中曲线取的是它与 13 条神谕的最高相似度；峰值只能说明外来视角下的语言接近，不能读成这名角色拥有一条命定。</p>}
      <p><b>词频峰：</b>{tfValue > 0 ? explainPeak(tf, '词频') : '整条词频线没有正值，说明这个角色的台词没有稳定复述自有神谕的词面。此时不能用“没有词频峰”推出“没有剧情关联”。'}</p>
      <PeakRecords evidence={evidence?.tfidf} />
      <p><b>语义峰：</b>{explainPeak(sb, '语义')}</p>
      <PeakRecords evidence={evidence?.sbert} />
      {separated
        ? <p className="curve-peak-diff"><b>为什么错峰：</b>两个峰落在不同步骤：词频峰由具体字词触发，语义峰由整段行动和语境触发。错峰本身不是数据冲突，而是提示我们把“说到了神谕”和“做出了与神谕相近的事”分开。</p>
        : <p className="curve-peak-diff"><b>为什么同峰：</b>两种表示在同一步一起抬高，说明这一段既保留了神谕的词面，也处在相关行动或语境中；仍需用事件标记确认它是不是兑现。</p>}
    </div>
  );
}

function CharacterSpecial({ name }) {
  const special = CHARACTER_SPECIALS[name];
  if (!special) return null;
  return (
    <aside className="character-special">
      <h4>{special.title}</h4>
      {special.paragraphs.map((p, i) => <p key={i}>{renderRich(p)}</p>)}
      <p className="character-special-source">{special.evidence}</p>
      {special.figure && <div className="character-special-figure"><FigureCard fig={special.figure} /></div>}
    </aside>
  );
}

function CharCard({ x, compact, knifeScenes, peakEvidence }) {
  const rows = useCharacterData(x.name);
  // 每版本台词量（柱状）
  const byVersion = {};
  for (const r of rows || []) byVersion[r.version] = r.version_n_records;
  const countData = ['3.0', '3.1', '3.2', '3.3', '3.4', '3.5', '3.6', '3.7']
    .map((v) => ({ version: v, 台词量: byVersion[v] || 0 }));
  const curveData = (rows || []).map((r) => ({
    步序: r.step_index, 词频加权: r.tfidf_own, 语义向量: r.sbert_own,
    version: r.version, task: r.task, title: r.step_title,
    events: EVENT_FLAGS.filter((f) => r[f.key]).map((f) => f.name),
  }));
  // 版本边界（竖虚线）+ 版本尺（图下方按出场次数比例分段，替代原先挤在轴内的标签）
  const boundaries = [];
  const verSegs = [];
  let lastV = null;
  for (const d of curveData) {
    if (d.version !== lastV) {
      boundaries.push({ step: d.步序, version: d.version });
      verSegs.push({ version: d.version, n: 0 });
      lastV = d.version;
    }
    verSegs[verSegs.length - 1].n += 1;
  }
  // 图上直接标注：每类事件取最早一次，且彼此在横轴上留出间距（最多 3 条）
  const marks = [];
  const usedSteps = new Set();
  const span = curveData.length > 1 ? curveData[curveData.length - 1].步序 - curveData[0].步序 : 0;
  const minGap = Math.max(6, span * 0.07);
  for (const f of ANNOT_FLAGS) {
    const row = (rows || []).find((r) => r[f.key] && !usedSteps.has(r.step_index));
    if (!row) continue;
    if (marks.some((m) => Math.abs(m.step - row.step_index) < minGap)) continue;
    usedSteps.add(row.step_index);
    marks.push({
      step: row.step_index, y: row.sbert_own, color: f.color,
      name: f.name, version: row.version, label: `${f.name} ${row.version}`,
    });
    if (marks.length >= 3) break;
  }
  // 事件清单：图上标注的行必列，再按「事件类型」各补一条代表（避免整表都是同一种事件），最后按步号升序
  const allEv = [];
  const seen = new Set();
  for (const d of curveData) {
    if (!d.events.length || seen.has(d.步序)) continue;
    seen.add(d.步序);
    allEv.push({
      步序: d.步序, version: d.version, marked: usedSteps.has(d.步序),
      事件类型: d.events.join('/'),
      标题: d.title, 任务: d.task,
    });
  }
  const evRows = allEv.filter((e) => e.marked);
  const shownTypes = new Set(evRows.map((e) => e.事件类型));
  for (const e of allEv) {
    if (evRows.length >= 8) break;
    if (e.marked || !e.事件类型 || shownTypes.has(e.事件类型)) continue;
    shownTypes.add(e.事件类型);
    evRows.push(e);
  }
  evRows.sort((a, b) => a.步序 - b.步序);
  return (
    <figure className="char-card">
      <div className="char-head">
        {PORTRAITS[x.name] && (
          // /materials/<slug>-portrait.png = 该角色官方立绘（圆形小头像）；?v=2 是缓存刷新用的查询串
          <img className="portrait" src={`/materials/${PORTRAITS[x.name]}-portrait.png?v=2`} alt={x.name}
            onError={(e) => { e.currentTarget.style.display = 'none'; }} />
        )}
        <strong>{x.name}</strong>
      </div>
      <p className="char-oracle">{oracleLine(x.name)}</p>
      <div className="tiny-chart">
        <ResponsiveContainer width="100%" height={104}>
          <BarChart data={countData} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#dbe2e7" />
            <XAxis dataKey="version" tick={{ fontSize: 11, fill: '#65717d' }} />
            <YAxis tick={{ fontSize: 11, fill: '#65717d' }} />
            <Tooltip content={<CharTip bar />} allowEscapeViewBox={{ x: false, y: true }}
              offset={{ x: 10, y: 14 }} isAnimationActive={false} wrapperStyle={{ zIndex: 6, pointerEvents: 'none' }} />
            <Bar dataKey="台词量" fill="#5b7f9e" />
          </BarChart>
        </ResponsiveContainer>
        <p className="chart-cap">每版本台词条数（横轴=版本；纵轴=条数）</p>
      </div>
      <div className="tiny-chart">
        <ResponsiveContainer width="100%" height={214}>
          <LineChart data={curveData} margin={{ top: 34, right: 14, left: -14, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#dbe2e7" />
            <XAxis dataKey="步序" type="number" domain={['dataMin', 'dataMax']} allowDecimals={false}
              tick={{ fontSize: 11, fill: '#65717d' }} tickCount={4} />
            <YAxis tick={{ fontSize: 11, fill: '#65717d' }} domain={[0, 'auto']} tickCount={4} />
            <Tooltip content={<CharTip />} allowEscapeViewBox={{ x: false, y: true }}
              offset={{ x: 10, y: 16 }} isAnimationActive={false} wrapperStyle={{ zIndex: 6, pointerEvents: 'none' }} />
            <Line type="monotone" dataKey="词频加权" stroke="#6f90b0" dot={false} strokeWidth={1.2} />
            <Line type="monotone" dataKey="语义向量" stroke="#b4551c" dot={false} strokeWidth={1.4} />
            {boundaries.map((b) => (
              <ReferenceLine key={`v-${b.step}`} x={b.step} stroke="#c3cdd6" strokeDasharray="2 3" />
            ))}
            {EVENT_FLAGS.map((f) => curveData
              .filter((d) => d.events.includes(f.name))
              .map((d) => (
                <ReferenceDot key={`${f.key}-${d.步序}`} x={d.步序} y={d.语义向量} r={2.4}
                  fill={f.color} stroke="white" strokeWidth={0.5} />
              )))}
            <EventCallouts marks={marks} />
          </LineChart>
        </ResponsiveContainer>
        <div className="chart-legend">
          <span><i style={{ background: '#6f90b0' }} />词频加权</span>
          <span><i style={{ background: '#b4551c' }} />语义向量</span>
        </div>
        <div className="ver-ruler" aria-hidden="true">
          {verSegs.map((s) => (
            <span key={s.version} style={{ flexGrow: s.n }}>{s.version}</span>
          ))}
        </div>
        <p className="chart-cap">与自己神谕的相似度（横轴=该角色第 N 次出场；竖虚线=版本分界，下方尺子标版本；彩点=事件类型；箭头=图上标注的事件，标题见下表）</p>
        {!compact && <p className="chart-note">兑现=配置里 confirmed 的兑现段；「神谕文本首现」可能由旁白或他人代念（不代表本角色自己念出）；「高光场景」取自 K 场景表，是社区口径的高光/虐心场景，不代表该步是悲剧。两条线分开是常态：词频线抬=这一步说到了神谕的词；语义线抬=只是语境相近（可能假峰）；两线同抬才算「语言上真的在说同一件事」。</p>}
        {!compact && (
          <div className="event-legend">
            {EVENT_FLAGS.map((f) => (
              <span key={f.key}><i style={{ background: f.color }} />{f.name}</span>
            ))}
          </div>
        )}
        <CurvePeakExplanation rows={rows} name={x.name} evidence={peakEvidence?.[x.name]} />
        {evRows.length > 0 && (
          <table className="event-table">
            <thead><tr><th>出场序</th><th>版本</th><th>事件</th><th>剧情标题</th></tr></thead>
            <tbody>
              {evRows.map((e) => (
                <tr key={e.步序} className={e.marked ? 'is-marked' : undefined}>
                  <td>{e.步序}</td><td>{e.version}</td>
                  <td>{e.marked ? '▶ ' : ''}{e.事件类型}</td><td>{e.标题 || e.任务}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {allEv.length > 0 && (
          <p className="event-note">共 {allEv.length} 个事件步；表中列 {evRows.length} 行（▶ = 图上箭头所指，其余为各事件类型的代表行）。</p>
        )}
      </div>
      <HighlightEvidence name={x.name} scenes={knifeScenes} compact={compact} />
      <CharacterSpecial name={x.name} />
      <figcaption><p>{x.note}</p></figcaption>
    </figure>
  );
}

const NLP_NOTE = '词频=词面重合，语义=整体语感；两者绝对值不可比（TF-IDF 0–0.22 / SBERT 0.54–0.72），所以只看排名。语义 top1 常是 O08 —— 它是 hub 句，天然靠近所有文本，不能读成归属。';

function OracleTip({ active, payload }) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload || {};
  return (
    <div className="char-tip">
      <div className="char-tip-h">{p.oid}</div>
      <div className="char-tip-b">词频 {Number(p.tfidf_raw).toFixed(3)}　语义 {Number(p.sbert_raw).toFixed(3)}</div>
    </div>
  );
}

// 单个角色：13 条神谕的两种表示对比（各自除以本角色最大值，只比形状）
function OracleBars({ name }) {
  const m = CHAR_ORACLE_MATRIX[name];
  if (!m) return null;
  const oids = Object.keys(ORACLES);
  const valsT = oids.map((o) => m.tfidf[o] || 0);
  const valsS = oids.map((o) => m.sbert[o] || 0);
  const minT = Math.min(...valsT), maxT = Math.max(...valsT, 1e-6);
  const minS = Math.min(...valsS), maxS = Math.max(...valsS, 1e-6);
  const norm = (v, lo, hi) => (hi - lo < 1e-9 ? 0.5 : (v - lo) / (hi - lo));
  const own = OWN_ORACLE[name] || [];
  const data = oids.map((oid) => ({
    oid: own.includes(oid) ? '★' + oid : oid,
    词频: +norm(m.tfidf[oid] || 0, minT, maxT).toFixed(3),
    语义: +norm(m.sbert[oid] || 0, minS, maxS).toFixed(3),
    tfidf_raw: m.tfidf[oid] || 0,
    sbert_raw: m.sbert[oid] || 0,
  }));
  return (
    <div className="oracle-bars">
      <ResponsiveContainer width="100%" height={216}>
        <BarChart data={data} layout="vertical" margin={{ top: 2, right: 6, left: 2, bottom: 0 }} barCategoryGap={1}>
          <XAxis type="number" hide domain={[0, 1]} />
          <YAxis type="category" dataKey="oid" width={44} tick={{ fontSize: 9, fill: '#39434d' }} interval={0} />
          <Tooltip content={<OracleTip />} allowEscapeViewBox={{ x: false, y: true }}
            offset={{ x: 8, y: 10 }} isAnimationActive={false} wrapperStyle={{ zIndex: 6, pointerEvents: 'none' }} />
          <Bar dataKey="词频" fill="#6f90b0" barSize={4} />
          <Bar dataKey="语义" fill="#b4551c" barSize={4} />
        </BarChart>
      </ResponsiveContainer>
      <p className="oracle-bars-cap">两种表示各自做 min–max 归一（★=自有神谕），只看两种表示内部谁高谁低；绝对值看上一行。</p>
    </div>
  );
}

function CharNlp({ name }) {
  const r = CHAR_ORACLE_RANK[name];
  if (!r) return null;
  const f = (v) => (v == null ? '—' : Number(v).toFixed(3));
  return (
    <div className="char-nlp">
      <div className="char-nlp-head">角色向量 × 神谕向量</div>
      {r.own.length ? (
        <p className="char-nlp-oracle">{r.own.map((id) => ORACLES[id] ? id + '「' + ORACLES[id].text + '」' : id).join('　')}</p>
      ) : (
        <p className="char-nlp-oracle">无自有神谕（外来视角：只算与 13 条神谕的最高相似度）</p>
      )}
      {r.own.length > 0 && (
        <p className="char-nlp-line">词频 {f(r.tfidf_cos)}（第 {r.tfidf}/13）　语义 {f(r.sbert_cos)}（第 {r.sbert}/13）</p>
      )}
      <OracleBars name={name} />
      <p className="char-nlp-note">{NLP_NOTE}</p>
    </div>
  );
}

// 同一组 2+ 人：自有神谕在各自曲线上的排名对比（越低越好）
function GroupBars({ names }) {
  const rows = names
    .map((nm) => ({ nm, r: CHAR_ORACLE_RANK[nm] }))
    .filter((x) => x.r && x.r.own.length > 0);
  if (rows.length < 2) return null;
  const data = rows.map(({ nm, r }) => ({ 角色: nm, 词频排名: r.tfidf, 语义排名: r.sbert }));
  return (
    <div className="oracle-bars">
      <ResponsiveContainer width="100%" height={170}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: -6, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#dbe2e7" />
          <XAxis dataKey="角色" tick={{ fontSize: 11, fill: '#39434d' }} />
          <YAxis domain={[0, 13]} tick={{ fontSize: 10, fill: '#65717d' }} tickCount={4} />
          <Tooltip isAnimationActive={false} />
          <Bar dataKey="词频排名" fill="#6f90b0" barSize={16} />
          <Bar dataKey="语义排名" fill="#b4551c" barSize={16} />
        </BarChart>
      </ResponsiveContainer>
      <p className="oracle-bars-cap">自有神谕在各自 13 条神谕里的排名（柱越短越好；横轴=同组成员）。</p>
    </div>
  );
}

function CharNlpGroup({ names }) {
  const rows = names.map((nm) => ({ name: nm, r: CHAR_ORACLE_RANK[nm] })).filter((x) => x.r);
  if (!rows.length) return null;
  const f = (v) => (v == null ? '—' : Number(v).toFixed(3));
  return (
    <div className="char-nlp">
      <div className="char-nlp-head">角色向量 × 神谕向量（同组对比）</div>
      <p className="char-nlp-oracle">
        {rows.map(({ name: nm, r }) => r.own.length
          ? nm + '：' + r.own.map((id) => ORACLES[id] ? id + '「' + ORACLES[id].text + '」' : id).join('　')
          : nm + '：无自有神谕').join('\n')}
      </p>
      <table className="char-nlp-table">
        <thead>
          <tr><th>角色</th><th>自有神谕</th><th>词频（相似度/排名）</th><th>语义（相似度/排名）</th><th>最像（词频 / 语义）</th></tr>
        </thead>
        <tbody>
          {rows.map(({ name: nm, r }) => (
            <tr key={nm}>
              <td>{nm}</td>
              <td>{r.own.length ? r.own.join('、') : '无'}</td>
              <td>{r.own.length ? r.tfidf_cos.toFixed(3) + ' / ' + r.tfidf + '/13' : '—'}</td>
              <td>{r.own.length ? r.sbert_cos.toFixed(3) + ' / ' + r.sbert + '/13' : '—'}</td>
              <td>{r.top_tfidf[0][0]} {f(r.top_tfidf[0][1])} / {r.top_sbert[0][0]} {f(r.top_sbert[0][1])}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <GroupBars names={names} />
      <p className="char-nlp-note">{NLP_NOTE}</p>
    </div>
  );
}

const RETRIEVAL_METHODS = [
  {
    name: '关键词',
    color: 'blue',
    what: '手工挑出的重点词，命中越多，分数越高；重点词会额外加权。',
  },
  {
    name: 'TF-IDF-char',
    color: 'blue',
    what: '把连续的 2–3 个汉字片段拿来比，不依赖分词；片段越少见，权重越高。',
  },
  {
    name: 'TF-IDF-word',
    color: 'amber',
    what: '按词和相邻词组比较，罕见词权重大；比字符片段更精确，也更依赖分词结果。',
  },
  {
    name: 'BM25',
    color: 'amber',
    what: '经典文本检索方法：重视罕见词，同时对过长的候选段做长度校正。',
  },
  {
    name: 'LSA（100 维）',
    color: 'green',
    what: '先把词频空间压缩成 100 个潜在方向，再比较整体主题；它会把相近词面揉到一起。',
  },
  {
    name: 'SBERT',
    color: 'green',
    what: '把神谕和每个剧情步骤分别变成句向量，再比较向量方向；目标是捕捉语义相近。',
  },
];

function RetrievalPurpose() {
  return (
    <section className="retrieval-purpose">
      <h3>为什么要做检索实验？</h3>
      <p>项目真正要问的不是“哪一步和神谕最像”，而是：给系统一条神谕，它能不能从 686 个剧情步骤里，找到这条神谕真正兑现的地方？</p>
      <p>相似度曲线只能告诉我们某一步像不像；检索实验还要检查它能不能把目标段排到前面。这样才能知道 NLP 是不是能帮人工阅读缩小范围，而不是把“直接念出原句”的步骤误当成兑现证据。</p>
    </section>
  );
}

function ChapterLead({ lead }) {
  if (!lead) return null;
  return (
    <div className="chapter-lead">
      <h3>{lead.question}</h3>
      <p>{lead.thesis}</p>
    </div>
  );
}

function FulfillmentTable({ data }) {
  const rows = data?.oracles || [];
  if (!rows.length) return null;
  return (
    <section className="fulfillment-table-wrap">
      <h3 className="block-title">13 条神谕的兑现总表</h3>
      <p className="fulfillment-table-note">这里展示的是当前分析口径：类型和兑现段来自人工整理后的配置；它用于回看全局结构，不等同于模型自动判定。「当前兑现段」写成 版本|任务|步骤号（例：3.4|英雄啊，回返那安宁的家乡|21 = 3.4 版本该任务的第 21 个剧情步骤）；末列 K 编号是场景表里的高光场景编号（K01–K36，同一编号全文指同一场景）。</p>
      <div className="table-scroll">
        <table className="fulfillment-table">
          <thead><tr><th>神谕</th><th>持有者</th><th>类型</th><th>当前兑现段</th><th>关联高光</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.oracle_id}>
                <td><strong>{r.oracle_id}</strong><br /><span>{r.text}</span></td>
                <td>{r.holder}</td>
                <td>{r.current_filled_type || '—'}</td>
                <td>{r.current_filled_fulfillment || '—'}</td>
                <td>{r.proposed_event_scene || (r.event_candidates || []).map((x) => x.scene_id).filter(Boolean).join('、') || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RetrievalMethodGuide() {
  return (
    <section className="method-guide" aria-label="检索方法说明">
      <h3 className="block-title">六种检索方法：各自看什么</h3>
      <p className="method-guide-note">这里的 LSA 和 SBERT 是两种独立方法，不是把两个模型串起来；v1/v2 没有 SBERT，v3 才把它加入同一组比较。</p>
      <div className="method-guide-list">
        {RETRIEVAL_METHODS.map((m) => (
          <article className={`method-guide-row method-guide-${m.color}`} key={m.name}>
            <h4>{m.name}</h4>
            <p><strong>它看什么：</strong>{m.what}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

const RETRIEVAL_VERSIONS = [
  {
    tag: 'v1', name: '第一版（旧结果）', change: '起点',
    target: '目标段：角色把神谕原句念出来的剧情步骤',
    pool: '686 个剧情步骤',
    methods: '5 个：关键词 / TF-IDF-char / TF-IDF-word / BM25 / LSA',
    evals: '13 个可评问题',
    best: '关键词 MRR 0.73',
    note: '开卷考试：原句就在候选文档里，字面方法必然占优',
  },
  {
    tag: 'v2', name: '诊断版 v2_mask', change: '去掉 query 里的原句',
    target: '同 v1（吟诵步）',
    pool: '686 个剧情步骤',
    methods: '5 个（同 v1）',
    evals: '13 个可评问题',
    best: '关键词 MRR 0.66',
    note: 'mask：把 query 里的神谕原句抹掉，只留关键词与弱提示',
  },
  {
    tag: 'v3', name: '正式版 v3', change: '换命中标准 + 剔除吟诵步 + 加语义向量',
    target: '目标段：神谕真正应验、被兑现的那一步',
    pool: '661 个（剔除 25 个含原句的吟诵步）',
    methods: '6 个：上面 5 个 + SBERT 语义向量',
    evals: '7 个可评问题',
    best: '关键词 MRR 0.13',
    note: '关卷考试：不能再靠原句，只能靠语义；结果 6 种方法全部失败',
  },
];

function ChapterOneIntro({ blocks, setup }) {
  return (
    <div className="ch01-intro">
      <p className="ch01-question">先不看图，先回答一个问题：一句话怎样才能变成可以比较的数据？</p>
      <div className="ch01-methods">
        {(blocks || []).map((b) => (
          <article className={`ch01-method ch01-method-${b.tone}`} key={b.label}>
            <div className="ch01-method-label">{b.label}</div>
            <h3>{b.title}</h3>
            <p>{renderMethod(b.body)}</p>
            <p className="ch01-method-limit"><span>边界</span>{renderMethod(b.limit)}</p>
          </article>
        ))}
      </div>
      {setup && <p className="ch01-setup">{renderMethod(setup)}</p>}
    </div>
  );
}

// 第 1 章：检索实验 v1→v2→v3 的版本时间线（我们自己的工作，放在正文后）
function RetrievalTimeline() {
  return (
    <div className="rt-wrap">
      <h3 className="block-title">检索实验的三个版本（v1 → v2 → v3）</h3>
      <div className="rt-timeline">
        {RETRIEVAL_VERSIONS.map((v, i) => (
          <div className="rt-card" key={v.tag}>
            <div className="rt-head">
              <span className="rt-tag">{v.tag}</span>
              <span className="rt-name">{v.name}</span>
            </div>
            <p className="rt-change">{i === 0 ? '起点' : '改动：' + v.change}</p>
            <dl className="rt-list">
              <dt>要找的段落</dt><dd>{v.target}</dd>
              <dt>候选池</dt><dd>{v.pool}</dd>
              <dt>方法</dt><dd>{v.methods}</dd>
              <dt>可评问题</dt><dd>{v.evals}</dd>
              <dt>最好结果</dt><dd>{v.best}</dd>
            </dl>
            <p className="rt-note">{v.note}</p>
            {i < RETRIEVAL_VERSIONS.length - 1 && <span className="rt-arrow">→</span>}
          </div>
        ))}
      </div>
      <p className="rt-foot">v3_control = 用 v3 的“目标兑现段”、但不剔除吟诵步的对照（13 个可评、关键词 MRR 0.48）——用来隔离「剔除吟诵步」这一步的影响。v3 只剩 7 个可评问题，所以 v3 的 0.13 与 v1 的 0.73 不能直接横比。</p>
    </div>
  );
}

function Section({ ch, data, knifeScenes, fulfillment, citationCoding, keyEvents, coverage, farewell, peakEvidence, baselineB2, styleCompare, rubySummary, openQuestions }) {
  const c = CONTENT[ch.id] || {};
  const chars = CHARACTER_FIGS[ch.id] || [];
  const byName = Object.fromEntries(chars.map((x) => [x.name, x]));
  const groups = CHAR_GROUPS[ch.id] || [];
  return (
    <section id={ch.id} className={`chapter${ch.id === 'ch01' ? ' chapter-one' : ''}`}>
      <header className="chapter-head">
        <span className="chapter-num">第 {ch.num} 章</span>
        <h2>{ch.title}</h2>
        <p className="kicker">{ch.kicker}</p>
      </header>
      <ChapterLead lead={CHAPTER_LEADS[ch.id]} />
      {ch.id === 'ch01' && <ChapterOneIntro blocks={c.intro} setup={c.setup} />}
      {ch.id === 'ch01' && <RetrievalPurpose />}
      {groups.length === 0 && c.pieces?.length > 0 && (
        <div className="prose">
          {ch.id === 'ch01' && <h3 className="block-title ch01-section-title">检索实验：我们到底在检索什么</h3>}
          {c.pieces?.map((p, i) => <p key={i}>{renderRich(p)}</p>)}
        </div>
      )}
      {ch.id === 'ch01' && <RetrievalMethodGuide />}
      {ch.id === 'ch01' && <RetrievalTimeline />}
      {ch.id === 'ch05' && <FulfillmentTable data={fulfillment} />}
      {ch.id === 'ch05' && <CodaTopics topics={c.topics} farewell={farewell} openQuestions={openQuestions} />}
      {ch.id === 'ch01' && <BaselineComparison data={baselineB2} />}
      {ch.id === 'ch01' && <StyleCompareCard data={styleCompare} />}
      {ch.id === 'ch01' && <RubyPairsCard data={rubySummary} />}
      {ch.id === 'ch04' && <CitationLedger data={citationCoding} />}
      {groups.map(([names, idx], gi) => (
        <div className={`char-row${names.length > 1 ? ' multi' : ''}`} key={gi}>
          {GROUP_LABELS[ch.id]?.[gi] && <h3 className="group-title">{GROUP_LABELS[ch.id][gi]}</h3>}
          <div className="char-left">
            {names.map((n) => byName[n] && <CharCard x={byName[n]} key={n} compact={names.length > 1} knifeScenes={knifeScenes} peakEvidence={peakEvidence} />)}
          </div>
          {names.length > 1 && (
            <div className="event-legend group-legend">
              {EVENT_FLAGS.map((f) => (
                <span key={f.key}><i style={{ background: f.color }} />{f.name}</span>
              ))}
            </div>
          )}
          {names.length > 1 && (
            <p className="group-note">三条曲线读法相同：词频线抬=这一场戏说到了神谕的词；语义线抬=只是语境相近（可能假峰）；两线同抬才算「语言上真的在说同一件事」。兑现=配置里 confirmed 的兑现段；「神谕文本首现」可能由旁白或他人代念；「高光场景」取自 K 场景表。</p>
          )}
          <div className="char-right">
            <h3 className="char-names">{names.join(' × ')}</h3>
            {splitNarrative(c.pieces?.[idx] || '').map((p, pi) => <p key={pi}>{renderRich(p)}</p>)}
            {names.length > 1 ? <CharNlpGroup names={names} /> : <CharNlp name={names[0]} />}
          </div>
        </div>
      ))}
      {(c.figures || []).length > 0 && (
        <div className="figure-block">
          <FigureBlockIntro intro={c.figureIntro} />
          <h3 className="block-title">关键图</h3>
          <div className="figure-grid">
            {(c.figures || []).map((f) => <FigureCard fig={f} key={f.src + f.title} />)}
          </div>
          {ch.id === 'ch04' && <CoverageTable rows={coverage} />}
          {ch.id === 'ch04' && <KeyEventLedger data={keyEvents} />}
        </div>
      )}
      {(c.post || []).length > 0 && (
        <div className="prose post-prose">
          <h3 className="block-title">把两个表示放在一起看</h3>
          {c.post.map((t, i) => <p key={i}>{renderRich(t)}</p>)}
        </div>
      )}
      {(c.lateFigures || []).length > 0 && (
        <div className="figure-block late-figures">
          <div className="figure-grid">
            {c.lateFigures.map((f) => <FigureCard fig={f} key={f.src + f.title} />)}
          </div>
        </div>
      )}
    </section>
  );
}

function Synopsis() {
  return (
    <section id="ch00" className="chapter synopsis">
      <header className="chapter-head">
        <span className="chapter-num">第 0 章</span>
        <h2>故事梗概：被循环困住的世界</h2>
        <p className="kicker">先看故事，再看数据</p>
      </header>
      <div className="synopsis-grid">
        <div className="synopsis-text">
          {SYNOPSIS.map((p, i) => <p key={i}>{p}</p>)}
        </div>
        <div className="portraits">
          {/* /materials/bai-e-portrait.png = 白厄官方立绘（梗概页装饰图，缺失时 onError 隐藏） */}
        <figure><img src="/materials/bai-e-portrait.png" alt="白厄" onError={(e) => { e.currentTarget.style.display = 'none'; }} /><figcaption>白厄：被选中的人</figcaption></figure>
          {/* /materials/xi-lian-portrait.png = 昔涟官方立绘（梗概页装饰图） */}
        <figure><img src="/materials/xi-lian-portrait.png" alt="昔涟" onError={(e) => { e.currentTarget.style.display = 'none'; }} /><figcaption>昔涟：讲述者与写书人</figcaption></figure>
          {/* /materials/xia-die-portrait.png = 遐蝶官方立绘（梗概页装饰图） */}
        <figure><img src="/materials/xia-die-portrait.png" alt="遐蝶" onError={(e) => { e.currentTarget.style.display = 'none'; }} /><figcaption>遐蝶：把预言读反的人</figcaption></figure>
        </div>
      </div>
    </section>
  );
}

export default function App() {
  const [screens, setScreens] = useState(null);
  const [knifeScenes, setKnifeScenes] = useState(null);
  const [fulfillment, setFulfillment] = useState(null);
  const [citationCoding, setCitationCoding] = useState(null);
  const [keyEvents, setKeyEvents] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [farewell, setFarewell] = useState(null);
  const [peakEvidence, setPeakEvidence] = useState(null);
  const [baselineB2, setBaselineB2] = useState(null);
  const [openQuestions, setOpenQuestions] = useState(null);
  const [styleCompare, setStyleCompare] = useState(null);
  const [rubySummary, setRubySummary] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    // /data/screens.json：章节级基础数据快照（标题/摘要/计数），当前页面正文主要用 CONTENT 常量， 这个请求只保留兼容
    fetch('/data/screens.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setScreens)
      .catch((e) => setError(e.message));
    fetch('/data/knife-scenes.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => setKnifeScenes(d.scenes || []))
      .catch((e) => setError(e.message));
    fetch('/data/oracle-fulfillment.v2.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setFulfillment)
      .catch((e) => setError(e.message));
    fetch('/data/oracle-citation-coding.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setCitationCoding)
      .catch((e) => setError(e.message));
    fetch('/data/key-events.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setKeyEvents)
      .catch((e) => setError(e.message));
    fetch('/data/f10_coverage.csv')
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((text) => setCoverage(parseSimpleCsv(text)))
      .catch((e) => setError(e.message));
    fetch('/data/farewell-similarity.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setFarewell)
      .catch((e) => setError(e.message));
    fetch('/data/character-peak-evidence.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => setPeakEvidence(d.characters || {}))
      .catch((e) => setError(e.message));
    fetch('/data/baseline-b2-scores.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setBaselineB2)
      .catch((e) => setError(e.message));
    fetch('/data/l3-open-questions.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setOpenQuestions)
      .catch((e) => setError(e.message));
    fetch('/data/style-compare-results.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setStyleCompare)
      .catch((e) => setError(e.message));
    fetch('/data/ruby-pairs.jsonl')
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((text) => setRubySummary(summarizeRubyPairs(text)))
      .catch((e) => setError(e.message));
  }, []);
  const byId = Object.fromEntries((screens?.chapters || []).map((c) => [c.id, c]));
  return (
    <>
      <header className="hero">
        <div className="hero-bg" aria-hidden="true" />
        <div className="hero-inner">
          <p className="eyebrow">崩坏：星穹铁道 · 翁法罗斯 3.0–3.7 · NLP 课程项目</p>
          <h1>命定如何被写进语言</h1>
          <p className="lede">神谕、引用与兑现：26,332 条记录（台词/旁白/选项）里，「命定」是一套可以被测量、被接管、被改写的语言实践。</p>
          <div className="meta-chips">
            <span>26,332 条记录</span><span>13 条神谕</span><span>14 个角色全量精读</span><span>6 章 · 每图旁标轴</span>
          </div>
        </div>
      </header>

      <nav className="chapter-nav">
        {CHAPTERS.map((c) => (
          <a key={c.id} href={`#${c.id}`}>第 {c.num} 章</a>
        ))}
      </nav>

      <main>
        <Synopsis />
        {CHAPTERS.slice(1).map((ch) => (
          <Section key={ch.id} ch={ch} data={byId[ch.id]} knifeScenes={knifeScenes} fulfillment={fulfillment} citationCoding={citationCoding} keyEvents={keyEvents} coverage={coverage} farewell={farewell} peakEvidence={peakEvidence} baselineB2={baselineB2} styleCompare={styleCompare} rubySummary={rubySummary} openQuestions={openQuestions} />
        ))}
        {error && <p className="error">章节数据加载失败：{error}（图表与正文仍可阅读）</p>}
      </main>

      <footer className="footer">
        <p>数据与图注均可回溯：每张图旁标注了横轴/纵轴/如何判好坏/本图结论。</p>
        <p>语料、模型与图-数据配对：见项目根目录 <code>INDEX.md</code>；本页只做课程展示，不公开游戏原文。</p>
      </footer>
    </>
  );
}

