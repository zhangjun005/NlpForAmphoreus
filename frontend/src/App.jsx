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
  { id: 'ch04', num: '4', title: '对偶、长线与旁观者：交换、引用链与外来视角', kicker: '海瑟音×刻律德菈 / 阿格莱雅×赛飞儿 / 列车组' },
  { id: 'ch05', num: '5', title: '收束：13 条兑现、明天见、水晶花', kicker: '告别、明天与收梢' },
];

const SYNOPSIS = [
  '翁法罗斯是一座被黑潮围困的世界：大地沉入永夜，唯剩圣城奥赫玛在刻法勒的庇佑下亮着最后一点光。十二泰坦早已疯狂，人们把希望押在「逐火之旅」上——由黄金裔接过十二枚火种、完成「再创世」，让破碎的世界重获新生。每位黄金裔生来都背着一句神谕，命定像钉子一样钉在他们身上；可「再创世」本身是一场骗局，世界被锁在一次次重演的循环里。',
  '黄金裔们逐一登场，也逐一退场。万敌亲手终结了悬锋王朝，也把「背后负创而死」的弱点亲手交给了白厄；阿格莱雅以「最后一次沐浴」收场，而她的谢幕是另一场设计好的死；缇宝把「明天见」当作最伟大的预言送给众生；那刻夏把自己炼进「理性」的火种；海瑟音与刻律德菈各执一条词序颠倒的镜像神谕；赛飞儿用一个谎言维系奥赫玛的永昼；遐蝶把「相拥之后便是永恒的离别」读成「拥抱就是爱」；风堇接过「天空」，荒笛把「大地」留给后来者。',
  '来自星穹列车的开拓者、三月七与丹恒，原本只是误入此地的外来客，却在送别一位位黄金裔的路上，变成愿意接过「负世」职责的参与者。真正撑起三千万次轮回的是白厄与昔涟：白厄一次次回到起点，昔涟把「岁月」剪成可以重写的一页，替他把「救世主」的预言写成希望。最终白厄亲手把「救世主」之名交了出去；昔涟则把自己的「收梢」写成「起始」。',
  '故事落到一本叫《如我所书》的书上：它起初只是昔涟童年那副神谕牌册，后来成了记录银河众生记忆的书；被写下的英雄，最终成了自己写书的人。「明天见」也一路改写：从母亲临终的安慰、从遐蝶口中那个「善意的谎言」，变成黄金裔们共同的预言与誓言——结尾没有句点，只有一句「明天见，乘以一千」。',
];

const CONTENT = {
  ch01: {
    left: 'text',
    pieces: [
      '全文只用两种方式表示文字。词频加权（TF-IDF）把一段话拆成词、按「这个词在本段出现得多不多、在整个语料里稀不稀有」给权重，整段变成一个稀疏向量；它的前提是「词袋」——只看词出现没有、不看词序。语义向量（句向量）用一个模型把整句话压成向量，意思越接近，向量方向越接近；这个模型属于 SBERT（Sentence-BERT，基于 BERT 的句子向量模型）这一类，本文用 bge-small-zh-v1.5（512 维）。两种向量之间用余弦相似度比较——余弦相似度就是两个向量夹角的余弦，越接近 1 说明方向越一致、越像；这是「怎么比」，不是第三种方法。',
      '在 26,332 条记录（台词/旁白/选项）上拟合的是：词表与词权重（11,737 维）、语义压缩模型（LSA/SVD，100 维：对词频矩阵做奇异值分解、保留前 100 个成分，得到压缩后的语义表示）、若干相似度矩阵。拿来用、没有训练的是预训练的语义向量模型（只推理、不微调）；角色向量是把某角色全部台词向量取平均得到的质心，是派生结果。检测器 A/B1/B2 是规则+特征打分，不是训练出来的模型；74 条标注只用于评测。',
    ],
    figures: [
      {
        src: '/figures/f1_level_scores.png',
        title: 'f1 等级-分数箱线',
        axes: '横轴是人工显著等级（0=可忽略、1=弱、2=中、3=最强），纵轴是检测器的标准化分数：把原始分减均值、再除以标准差得到的 z 分数，0 就是全库平均。',
        judge: '箱体随等级单调上移、0 级最低 3 级最高 = 检测器方向与人工一致（好）；各级重叠、没有趋势 = 不可靠（坏）。方法上：A/B1 是规则+特征打分，不是训练出来的模型；74 条标注只用于评测，所以只能看方向一致性，不能当准确率。',
        conclusion: 'B1 从 0 级 −0.68 升到 3 级 0.70，A 只从 −0.28 到 0.23 → B1 方向更清楚，但都只是趋势，不是准确率。',
      },
      {
        src: '/figures/f15a_retrieval_mrr.png',
        title: '神谕检索：各方法的 MRR',
        axes: '横轴是检索方法（按 variant 分组），纵轴是 MRR。MRR 是排序指标（Mean Reciprocal Rank）：正确答案在返回结果里排第 1 得 1 分、排第 2 得 1/2、排第 k 得 1/k，再对所有可评问题取平均——1 表示每次都排第一，0 表示从没进前列。',
        judge: '0.5 以上才说明常把正确答案排进前两名，0.1 以下基本等于没找到。它评的是「排序好不好」，不是「相似度算得对不对」。',
        conclusion: 'v3 组 6 种方法全部 ≤0.13（都失败）；对照组关键词 0.48、词频加权 0.39（相对好，但池里留着吟诵干扰项）。',
      },
      {
        src: '/figures/f15b_retrieval_recall.png',
        title: '神谕检索：Recall@k',
        axes: '横轴是 k（前 k 名），纵轴是 Recall@k。Recall@k 是命中率：返回的前 k 条结果里出现正确答案的比例——k=1 相当于「第一名就必须对」，k 越大越宽松。每条线是一种检索方法。',
        judge: '曲线越早抬到 1 说明正确答案越常出现在前面；v3 各方法在 k 增大时才慢慢抬，说明正确答案普遍排得很后。',
        conclusion: 'Recall@k 与 MRR 同向：v3 在事件级检索上失败，不是排序小瑕疵，而是正确答案根本没被排到前面。',
      },
    ],
    post: [
      '两个表示要一起用，最干净的证据是两条镜像神谕：O10「汝将长眠于涛声中，于天地境界之海完成征服」（海瑟音）与 O11「汝将于天地境界之海完成征服，长眠于涛声中」（刻律德菈）。两句用词相同、只换语序，所以词频加权给出的两条曲线在 686 步上逐点相等（最大差 0），语义向量也只给微小差异（平均 0.005、最大 0.018）——只看词或只看语义，都分不开这两条命定。（O01–O13 是全篇 13 条神谕的编号，按报告内顺序排列，后文提到某条命定都用这个编号。）',
    ],
    lateFigures: [
  {
          src: '/figures/f14a_mirror_tfidf.png',
          title: 'O10 / O11 的镜像曲线：词频加权',
          axes: '横轴是全局步序 1–686，纵轴是与神谕的余弦相似度；实线 O10（海瑟音），虚线 O11（刻律德菈）。',
          judge: '词频加权是词袋，语序被完全丢弃——两条命定只换了语序，所以曲线逐点相等，视觉上完全重合。重合对「区分 O10/O11」是坏，对「证明词面与语序无关」是好。',
          conclusion: '686 个点逐点相等（最大差 0）→ 词频加权完全分不开这两条命定。',
        },
        {
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
        src: '/figures/f7a_bai_lines.png',
        title: '白厄：台词量（柱）与出场步骤（线）',
        axes: '横轴是版本 3.0–3.7，柱子是台词条数，折线是出场步骤数。',
        judge: '台词高说明这一版是主场，折线高说明出场的剧情步骤多；3.1 台词 278 条、步骤 24 个，是「在场但不抢戏」的版本。',
        conclusion: '3.0 台词最多（634 条）且步骤最多（56 个），而 3.5 是 0 条 0 步——缺席本身就是信号：这一版白厄一句话都没有，戏份由别人转述。',
      },
      {
        src: '/figures/f7b_bai_forms.png',
        title: '白厄：语言形态构成（堆叠）',
        axes: '横轴是版本，纵轴是台词条数，按角色的语言形态（form 字段）堆叠。',
        judge: '同一版本里出现多种形态 = 同一个人用不同声音说话；非本体形态越多，身份分裂越强。形态是文本字段计数，不是模型输出。',
        conclusion: '3.4 的 711 条被拆成白厄本体 425、卡厄斯兰那 224、心中的英雄 49、盗火行者 8、幼年 4——身份峰值在这一版，而不是 3.0 的台词峰值。',
      },
      {
        src: '/figures/f7c_bai_address.png',
        title: '白厄：称呼词命中（自己的台词）',
        axes: '横轴是版本，纵轴是称呼词在白厄自己台词里的命中次数。',
        judge: '「老师」下降、「伙伴 / 英雄」上升 = 关系从师徒转向同伴；这是纯词面统计，和 TF-IDF 那条曲线看的是同一类证据。',
        conclusion: '「老师」在 3.0 命中 40 次后回落，3.3–3.4 出现「伙伴 / 英雄」——称呼的变化点（3.3 起）比台词量的峰值更早。',
      },
      {
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
        src: '/figures/f8a_xi_lines.png',
        title: '昔涟：台词量（柱）与出场步骤（线）',
        axes: '横轴是版本 3.0–3.7，柱子是台词条数，折线是出场步骤数。',
        judge: '台词与步骤同步上涨 = 从片段式出场变成主要叙述者；只看条数会漏掉「她每场说多长」的变化。',
        conclusion: '从 3.0 的 92 条 / 11 步涨到 3.4 之后的高位（3.4 起她开始承担讲述），数量与在场深度一起上升。',
      },
      {
        src: '/figures/f8b_xi_forms.png',
        title: '昔涟：语言形态构成（堆叠）',
        axes: '横轴是版本，纵轴是台词条数，按语言形态堆叠。',
        judge: '形态条的切换点越清楚，越能说明语言阶段在变；「迷迷」的断句体与「讲述者」是两套说话方式，形态字段能直接分开。',
        conclusion: '3.0–3.3 几乎全是「迷迷」，3.4 之后切到「记忆形态 / 往昔的涟漪」，3.7 再出现另一套形态——三个切换点都能在图上指出来。',
      },
      {
        src: '/figures/f8c_xi_address.png',
        title: '昔涟：称呼词命中（自己的台词）',
        axes: '横轴是版本，纵轴是称呼词在昔涟自己台词里的命中次数。',
        judge: '早期多用「迷迷」式自称与短称呼，后期转向对「你 / 开拓者」的直接对话；称呼变化对应她从旁观者走向讲述者。',
        conclusion: '「开拓者」类称呼在 3.4 之后抬升，与形态切换点同相位；词面统计和 TF-IDF 曲线是同一套视角。',
      },
      {
        src: '/figures/f8d_xi_detector.png',
        title: '昔涟：所在步骤的检测器分数',
        axes: '横轴是版本，纵轴是所在步骤的检测器平均分（A / B1；检测器是规则+特征打分，不是训练出来的模型），虚线是 B1 前 100 命中率。',
        judge: '分数上升对应语言从短句走向长句讲述，但分数只是语言突变强度，不等于感人程度；A/B1 是规则+特征打分。',
        conclusion: '3.4 之后分数与命中率抬升，与「迷迷 → 讲述者」的形态切换同相位——检测器与形态字段互相印证，而不是互相替代。',
      },
      {
        src: '/figures/f13_crystal_flower_semantic.png',
        title: 'f13 水晶花曲线',
        axes: '横轴是全局步序 1–686，纵轴是与 K36 原文的余弦相似度，词频加权与语义向量各一条线。',
        judge: '留一法（leave-one-out）=把 K36 自己那一步从 686 步池里剔除再算，否则它会和自身相似度=1 形成自匹配峰，因此图里只有 685 行。排除之后峰只能来自主题重叠：峰在 3.7 结尾 = 与「收梢」主题真实重叠（正常）；峰在 3.5 闪回区 = 可疑——判据是「语义线抬、词频线不抬」，说明只是语义泛化而不是主题重叠。',
        conclusion: '词频加权峰在步序 663（3.7 结尾），不在 K36 步；3.5 闪回区还有一批语义向量假峰。',
      },
    ],
  },
  ch04: {
    left: 'figure',
    pieces: [
      '海瑟音与刻律德菈：O10 属海瑟音、O11 属刻律德菈，两条话用词相同、只换语序。但引用分布极不对称：刻律德菈本人 0 次引用神谕，O11 全篇唯一一次出现是海瑟音替她念的（#20228）。兑现也交换了：刻律德菈死于「天地境界之海，一汪浅浅的死水」（#20339–#20340），「完成征服」却落空（#20353）；海瑟音献出余生的清醒与自由（#19814）。半句交换的动作是刻律德菈亲手完成的：赠送「天地境界之海」（#20322）、交付「天外的大海」（#20354）。这一组要记住的结论是：归属由「谁引用、谁兑现、把命定交给谁」决定，而不是词语。表示层同样给出证据：词频加权的两条曲线逐点相等（词袋对语序完全盲），语义向量只差 0.018（句向量对语序只略敏感）——所以两种表示都分不开这对镜像，必须靠引用/兑现的行为事实。质心上也一样：两人对 O10/O11 的词频值各自完全相等（0.102 / 0.076），语义差 ≤0.004，海瑟音甚至更接近 O11（0.684 vs 0.680）。',
      '阿格莱雅完成最完整的引用链：「汝将最后一次沐浴……」（#7458）→ 故人之音把「汝」换成「我」（#14241–#14242）→ 结局宣告「我将最后一次沐浴……现在，是时候将其兑现了」（#16615）；她的退场还接在 K06 遗书与白厄「更好的人」悼词（#12683–#12703、#12746–#12781）之后，不是只有金句。赛飞儿的「千年永昼」只是一次时间短语删改（#14400→#14570）；O08 的「分文」就是她的硬币（#10329–#10342），被夺走后她才失速而死（#14558→#14577–#14578）。引用链上的抬升是词频线与语义线一起抬——因为引用保留了原句的词；而「千年永昼」只是一次短语删改，两线变化都不大。质心上阿格莱雅 O01 词频第 1（0.140，全表最高档之一）、语义第 5；赛飞儿 O08 两种表示都第 1（0.065 / 0.659）——词面重合能认出「她确实反复说那句话」，但认不出归属。',
      '列车组：开拓者 3,058 条里 79.5% 是玩家选项，真实对白与短信只有 626 条；三月七 3.1/3.3 零台词（幽灵期）；丹恒 1,541 条含 89 条「丹枫」，3.6 承接大地火种（荒笛 → 丹恒）。所以列车组单列、不与黄金裔比较：他们的主线塑造在翁法罗斯之外。注意他们的曲线不是「自有命定曲线」，而是「与 13 条神谕的最高相似度」（没有自有神谕时的替代口径），别把它读成第 14 条命定。质心上他们没有自有神谕：词频 top1 都是 O01（0.050 / 0.031）、语义 top1 都是 O08（0.676 / 0.669）——这是 hub 句效应，不是「他们像这条命定」。',
      '风堇是 O07「在彩虹桥的尽头，天空之子将缝补晨昏」的持有者：她把「缝补晨昏」解释成医疗行为（#13042），在 3.3 留下天空、降下虹光（#14642–#14643），并由丹恒宣告应验（#14656–#14657）。她的兑现不是自己喊出来的，而是被他人见证、由他人代言的——这也是「兑现」与「本人引用」不同的地方。图上她 3.3 的峰在留天空、降虹光附近；但宣布应验的那句是丹恒说的，所以词频线抬的地方并不等于「她本人引用」的位置。质心上 O07 词频第 1（0.216，全表最高）、语义却排第 12（0.605）：台词里反复出现「天空/彩虹桥/缝补」这类词，语义空间反而被 hub 句吸走——词面高频不等于命定归属。',
    ],
    figures: [
      {
        src: '/figures/f4_citation_stage.png',
        title: 'f4 引用台账（对偶与长线）',
        axes: '横轴是剧情顺序，纵轴是引用阶段（原文出现、他人解释、本人引用、结局宣告、改写）。',
        judge: '阶段从「原文出现/他人解释」移到「本人引用/结局宣告」= 接管完成（好）；停在他人/旁白 = 没接管。方法上：这些阶段是人工按引用编码表打的标签，不是模型输出；f4 与相似度曲线不是同一个指标，不能互相印证。',
        conclusion: '本人引用 19/34、结局宣告 8 条，末次引用时本人 8/13——方向对，但只是弱趋势。',
      },
      {
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
    pieces: [
      '13 条神谕的兑现类型是：字面 10、反转 2、错位 1（合计 13）；另外有三个「结构标签」不计入类型：O03 双线、O06 追认、O13 两段。类型是人工读文本判的，相似度只用来找候选段——两者不能互相替代。',
      '专题一：「明天」与「明天见」。「明天见」不是一句客套：它起于白厄 3.0 的道别（#4211），缇宝第一次说是对商人的客套（#5259），母亲临终那句（#6876）被改写成「世上最伟大的预言」（#8077），最后在 3.7 由群体说出（#25271、#25778、#25779「乘以一千」），开拓者接「从今以后，不再有离别」（#25781）。把它按说话人拆开看：全库「明天」108 条（先按 record 匹配、再人工剔除 2 条跨词误报，110→108），缇宝 32 条、昔涟 17 条、白厄 13 条；而昔涟谈「明天」17 次、只说 1 次「明天见」——制造明天的人几乎不说那句口号。',
      '专题二：角色曲《昔涟》。把歌词当作独立的语料（24 条歌词记录，#26218–#26241）放进同一套向量空间后：14 个角色里离歌词最近的是昔涟自己（0.586），昔涟各版本里 3.7 最接近歌词（0.615）；但歌词与 13 条神谕最高的却是 O04（0.484），不是她自己的 O13（0.416）——角色曲更像在唱「死亡与告别」的母题，而不是复述自己的命定。这也说明相似度只回答「语言上像谁」，不回答「这首歌在讲什么」。',
      '专题三：水晶花寓言。这是改写最完整的演示：「水晶花」一词全篇只出现 11 次、全部在 3.7、全部由昔涟说；三版最像的角色都是昔涟（0.58–0.63），最像的神谕却是 O04（0.52–0.54），不是 O13。三版的句向量相似度 0.79–0.87、词频加权只有 0.28–0.47——改写换掉了词、保住了意思；f13 的「假峰」是同一机制：语义线在 3.5 抬头而词频线不动。《如我所书》把这一切收进口袋：名字最早来自昔涟童年的神谕牌册（#15977–#15978），最后成了银河级的记录（#25648）；结尾的 14 人名单（#26119–#26122）里包含开拓者；而「十三位英雄」（#26176）的计数不含他——13 = 11 位黄金裔 + 三月七 + 丹恒，开拓者是写书的人/见证者。',
      '边界：检索在事件级失效（7/13 可评、最好 MRR 0.132——MRR 是正确答案排名的倒数平均，1 表示每次都排第一），标注是 LLM 辅助（κ=0.788，Cohen kappa 是两次标注之间的一致性，越接近 1 越一致），相似度不是含义强度——这三条限制和数据本身一样重要：相似度是语言层的测量，能找候选、做对照，但不能替代读剧情。',
    ],
    figures: [
      {
        src: '/figures/f12_mingtian_timeline.png',
        title: 'f12 明天见时间线',
        axes: '横轴是版本 3.0–3.7，纵轴是出现次数。',
        judge: '母题从单版本扩散到多版本、且首尾都有 = 生命周期完整（好）；只集中在某一版本 = 局部用语。方法上：这是字符串计数，不是相似度——先按 record 匹配「明天见」，再人工剔除 2 条跨词误报（110→108）。',
        conclusion: '3.1 峰 9 次、3.7 5 次，中间零星——「起—收」两端高，符合「客套→预言→共同体誓言」的讲述。',
      },
      {
        src: '/figures/f13_crystal_flower_semantic.png',
        title: 'f13 水晶花曲线',
        axes: '横轴是全局步序（全库统一的剧情步序 1–686，与角色卡的「出场序」、正文的剧情步骤号都不是同一把尺子），纵轴是与 K36 原文的余弦相似度。',
        judge: '本图已用 leave-one-out 排除 K36 自己的步骤（685 行），所以不存在「峰落在 K36 步」；两条线同步在 3.7 结尾抬升 = 主题重叠可信，只有语义线抬、词频线不抬 = 语义泛化造成的假峰。',
        conclusion: '词频加权峰在 3.7 结尾，语义向量在 3.5 闪回区有假峰——两条线不同步，说明「相似」来源不同。',
      },
      {
        src: '/figures/f15a_retrieval_mrr.png',
        title: '检索失败是这份报告的边界之一（MRR）',
        axes: '横轴是检索方法，纵轴是 MRR（正确答案排名的倒数平均：排第 1 得 1、第 k 得 1/k；同组内越高越好，跨组不可比）。',
        judge: 'v3 组全部 <0.15 = 方法失败（这是结论，不是排名）。MRR 是排序指标，和余弦相似度不是一回事——相似度负责打分，MRR 负责评价打分好不好。',
        conclusion: 'v3 组最好 0.132，对照组 0.48——对照组「更好」但 gold 不同、池里有干扰，不能直接说词面方法更好。',
      },
      {
        src: '/figures/f15b_retrieval_recall.png',
        title: '检索失败：Recall@k 视角',
        axes: '横轴是 k（前 k 名），纵轴是 Recall@k。Recall@k 是命中率：返回的前 k 条结果里出现正确答案的比例——k=1 相当于「第一名就必须对」，k 越大越宽松。每条线是一种检索方法。',
        judge: '如果正确段落就在前几名，Recall@k 会随 k 迅速到 1；这里所有方法都要到很大的 k 才抬起来，说明正确答案普遍排在后面。',
        conclusion: '事件级检索的失败是系统性的：不是某一方法调参不好，而是「短神谕句 × 长剧情步骤」的粒度不匹配。',
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

const PORTRAITS = {
  白厄: 'bai-e', 万敌: 'wan-di', 那刻夏: 'na-ke-xia', 昔涟: 'xi-lian', 遐蝶: 'xia-die',
  缇宝: 'ti-bao', 海瑟音: 'hai-se-yin', 刻律德菈: 'ke-lv-de-la',
};

const HL = ['水晶花寓言', '明天见', '明天', '镜像神谕', '收梢即起始', '如我所书', '十三位英雄', '千年永昼',
  'O04', 'O06', 'O09', 'O13', '相拥之后', '拥抱就是爱', '三千万次轮回'];

function renderRich(text) {
  const pattern = new RegExp(`(${HL.join('|')})`, 'g');
  const parts = text.split(pattern);
  return parts.map((p, i) => (HL.includes(p) ? <strong className="hl" key={i}>{p}</strong> : <span key={i}>{p}</span>));
}

function FigureCard({ fig }) {
  const cls = fig.wide ? 'figure-card wide' : 'figure-card split';
  return (
    <figure className={cls}>
      <div className="figure-img">
        <img className={fig.wide ? 'wide' : undefined} src={fig.src} alt={fig.title} loading="lazy" />
      </div>
      <figcaption>
        <strong>{fig.title}</strong>
        <p>{fig.axes}</p>
        <p>{fig.judge}</p>
        <p>{fig.conclusion}</p>
      </figcaption>
    </figure>
  );
}

const CHARACTER_FIGS = {
  ch02: [
    { name: '白厄', img: '/figures/chars/白厄_mini.png', note: '沉默：唯一一次引用就是完整背出 O09 并交出名字；3.4 是身份分裂峰值' },
    { name: '万敌', img: '/figures/chars/万敌_mini.png', note: '递刀：3.1 交出弱点，两次兑现各一次' },
    { name: '那刻夏', img: '/figures/chars/那刻夏_mini.png', note: '配置把兑现段标得比原句早 46 步（两字段矛盾，追认只是其中一种读法）' },
  ],
  ch03: [
    { name: '昔涟', img: '/figures/chars/昔涟_mini.png', note: '讲述/写书：水晶花被改写两次，3.7 峰值' },
    { name: '遐蝶', img: '/figures/chars/遐蝶_mini.png', note: '读反：O04 从「永恒离别」改成「拥抱=爱」' },
    { name: '缇宝', img: '/figures/chars/缇宝_mini.png', note: '提炼：O02 是她从雅努斯的散文里提炼的箴言' },
  ],
  ch04: [
    { name: '海瑟音', img: '/figures/chars/海瑟音_mini.png', note: '镜像对：代念 O11，自己放弃征服、长眠守墓' },
    { name: '刻律德菈', img: '/figures/chars/刻律德菈_mini.png', note: '镜像对：0 次引用神谕，把「完成」换到律法上' },
    { name: '阿格莱雅', img: '/figures/chars/阿格莱雅_mini.png', note: '全链：汝→我→结局宣告，沐浴母题仅 7 次' },
    { name: '赛飞儿', img: '/figures/chars/赛飞儿_mini.png', note: '道具链：千年永昼是短语删改，O08=硬币' },
    { name: '开拓者', img: '/figures/chars/开拓者_mini.png', note: '旁观者：3,058 条里 79.5% 是选项' },
    { name: '三月七', img: '/figures/chars/三月七_mini.png', note: '旁观者：3.1/3.3 零台词（幽灵期）' },
    { name: '丹恒', img: '/figures/chars/丹恒_mini.png', note: '旁观者：1,541 条含 89 条「丹枫」' },
    { name: '风堇', img: '/figures/chars/风堇_mini.png', note: '被见证：O07 留天空、降虹光，由丹恒宣告应验' },
  ],
};

const CHAR_GROUPS = {
  ch02: [[['白厄'], 0], [['万敌'], 1], [['那刻夏'], 2]],
  ch03: [[['昔涟'], 0], [['遐蝶'], 1], [['缇宝'], 2]],
  ch04: [[['海瑟音', '刻律德菈'], 0], [['阿格莱雅', '赛飞儿'], 1], [['开拓者', '三月七', '丹恒'], 2], [['风堇'], 3]],
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

function CharCard({ x, compact }) {
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

function Section({ ch, data }) {
  const c = CONTENT[ch.id] || {};
  const chars = CHARACTER_FIGS[ch.id] || [];
  const byName = Object.fromEntries(chars.map((x) => [x.name, x]));
  const groups = CHAR_GROUPS[ch.id] || [];
  return (
    <section id={ch.id} className="chapter">
      <header className="chapter-head">
        <span className="chapter-num">第 {ch.num} 章</span>
        <h2>{ch.title}</h2>
        <p className="kicker">{ch.kicker}</p>
      </header>
      {groups.length === 0 && (
        <div className="prose">
          {c.pieces?.map((p, i) => <p key={i}>{renderRich(p)}</p>)}
        </div>
      )}
      {groups.map(([names, idx], gi) => (
        <div className={`char-row${names.length > 1 ? ' multi' : ''}`} key={gi}>
          <div className="char-left">
            {names.map((n) => byName[n] && <CharCard x={byName[n]} key={n} compact={names.length > 1} />)}
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
            <p>{renderRich(c.pieces?.[idx] || '')}</p>
            {names.length > 1 ? <CharNlpGroup names={names} /> : <CharNlp name={names[0]} />}
          </div>
        </div>
      ))}
      {(c.figures || []).length > 0 && (
        <div className="figure-block">
          <h3 className="block-title">关键图</h3>
          <div className="figure-grid">
            {(c.figures || []).map((f) => <FigureCard fig={f} key={f.src + f.title} />)}
          </div>
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
          <figure><img src="/materials/bai-e-portrait.png" alt="白厄" onError={(e) => { e.currentTarget.style.display = 'none'; }} /><figcaption>白厄：被选中的人</figcaption></figure>
          <figure><img src="/materials/xi-lian-portrait.png" alt="昔涟" onError={(e) => { e.currentTarget.style.display = 'none'; }} /><figcaption>昔涟：讲述者与写书人</figcaption></figure>
          <figure><img src="/materials/xia-die-portrait.png" alt="遐蝶" onError={(e) => { e.currentTarget.style.display = 'none'; }} /><figcaption>遐蝶：把预言读反的人</figcaption></figure>
        </div>
      </div>
    </section>
  );
}

export default function App() {
  const [screens, setScreens] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    fetch('/data/screens.json')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setScreens)
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
          <Section key={ch.id} ch={ch} data={byId[ch.id]} />
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

