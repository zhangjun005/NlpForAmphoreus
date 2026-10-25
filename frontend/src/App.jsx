import { useEffect, useState } from 'react';

const CHAPTERS = [
  { id: 'ch00', num: '0', title: '故事梗概：被循环困住的世界', kicker: '先看故事，再看数据' },
  { id: 'ch01', num: '1', title: '从剧情到数据：表示、模型与读图', kicker: '两种表示：词频加权与语义向量' },
  { id: 'ch02', num: '2', title: '承受命定的人：沉默、递刀与追认', kicker: '白厄 / 万敌 / 那刻夏' },
  { id: 'ch03', num: '3', title: '改写命定的人：讲述、读反与提炼', kicker: '昔涟 / 遐蝶 / 缇宝' },
  { id: 'ch04', num: '4', title: '对偶与旁观：交换、长线与外来者', kicker: '海瑟音×刻律德菈 / 阿格莱雅×赛飞儿 / 列车组' },
  { id: 'ch05', num: '5', title: '收束：13 条兑现、明天见、水晶花', kicker: '告别、明天与收梢' },
];

const SYNOPSIS = [
  '翁法罗斯是一座被黑潮围困的世界：大地沉入永夜，唯剩圣城奥赫玛在刻法勒的庇佑下亮着最后一点光。十二泰坦早已疯狂，人们把希望押在「逐火之旅」上——由黄金裔接过十二枚火种、完成「再创世」，让破碎的世界重获新生。每位黄金裔生来都背着一句神谕，命定像钉子一样钉在他们身上；可「再创世」本身是一场骗局，世界被锁在一次次重演的循环里。',
  '黄金裔们逐一登场，也逐一退场。万敌以「背后负创而死」的预言终结悬锋王朝；阿格莱雅把死亡当作最后一匹织物，在黄金浴池里谢幕；缇宝把「明天见」当作最伟大的预言送给众生；那刻夏把自己炼进「理性」的火种；海瑟音与刻律德菈各执一条词序颠倒的镜像神谕；赛飞儿用一个谎言维系奥赫玛的永昼；遐蝶把「相拥之后便是永恒的离别」读成「拥抱就是爱」；风堇接过「天空」，荒笛把「大地」留给后来者。',
  '来自星穹列车的开拓者、三月七与丹恒，原本只是误入此地的外来客，却在送别一位位黄金裔的路上，变成愿意接过「负世」职责的参与者。真正撑起三千万次轮回的是白厄与昔涟：白厄一次次回到起点，昔涟把「岁月」剪成可以重写的一页，替他把「救世主」的预言写成希望。最终白厄亲手把「救世主」之名交了出去；昔涟则把自己的「收梢」写成「起始」。',
  '故事落到一本叫《如我所书》的书上：它起初只是昔涟童年那副神谕牌册，后来成了记录银河众生记忆的书；被写下的英雄，最终成了自己写书的人。「明天见」也一路改写：从母亲临终的安慰、从遐蝶口中那个「善意的谎言」，变成黄金裔们共同的预言与誓言——结尾没有句点，只有一句「明天见，乘以一千」。',
];

const CONTENT = {
  ch01: {
    left: 'text',
    pieces: [
      '全文只用两种方式表示文字。词频加权（TF-IDF）把一段话拆成词、按「这个词在本段出现得多不多、在整个语料里稀不稀有」给权重，整段变成一个稀疏向量；它的前提是「词袋」——只看词出现没有、不看词序。语义向量（句向量）用一个模型把整句话压成向量，意思越接近，向量方向越接近；这个模型属于 SBERT（Sentence-BERT，基于 BERT 的句子向量模型）这一类，本文用 bge-small-zh-v1.5（512 维）。两种向量之间用余弦相似度比较——这是「怎么比」，不是第三种方法。',
      '在 26,332 条台词上拟合的是：词表与词权重（11,737 维）、语义压缩模型（LSA/SVD，100 维）、若干相似度矩阵。拿来用、没有训练的是预训练的语义向量模型（只推理、不微调）；角色向量是把某角色全部台词向量取平均得到的质心，是派生结果。检测器 A/B1/B2 是规则+特征打分，不是训练出来的模型；74 条标注只用于评测。',
      '两个表示要一起用，最干净的证据是两条镜像神谕：O10「汝将长眠于涛声中，于天地境界之海完成征服」（海瑟音）与 O11「汝将于天地境界之海完成征服，长眠于涛声中」（刻律德菈）。两句用词相同、只换语序，所以词频加权给出的两条曲线在 686 步上逐点相等（最大差 0），语义向量也只给微小差异（平均 0.005、最大 0.018）——只看词或只看语义，都分不开这两条命定。',
    ],
    figures: [
      {
        src: '/figures/f14_mirror_pair_O10_O11.png',
        title: 'f14 镜像曲线：词频加权完全重合',
        axes: '横轴：全局步序 1–686；纵轴：与神谕的余弦相似度。',
        judge: '越重合说明该表示越不受词序影响——对「区分 O10 与 O11」是坏，对「证明词面与语序无关」是好；分离越大说明有区分力。',
        conclusion: '686 个点逐点相等（最大差 0）→ 词频加权完全分不开这两条命定。',
      },
      {
        src: '/figures/f1_level_scores.png',
        title: 'f1 等级-分数箱线',
        axes: '横轴：人工显著等级 0/1/2/3；纵轴：检测器标准化分数（0 = 平均）。',
        judge: '箱体随等级单调上移、0 级最低 3 级最高 = 检测器方向与人工一致（好）；各级重叠、没有趋势 = 不可靠（坏）。',
        conclusion: 'B1 从 0 级 −0.68 升到 3 级 0.70，A 只从 −0.28 到 0.23 → B1 方向更清楚，但都只是趋势，不是准确率。',
      },
      {
        src: '/figures/f15_retrieval_v3.png',
        title: 'f15 检索对比',
        axes: '横轴：检索方法；纵轴：MRR（0–1，同组内越高越好，跨组不可比）。',
        judge: '同组里 MRR 越高越好；0.5 以上才算能把正确答案排进前几名，0.1 以下基本等于没找到。',
        conclusion: 'v3 组 6 种方法全部 ≤0.13（都失败）；对照组关键词 0.48、词频加权 0.39（相对好，但池里留着吟诵干扰项）。',
      },
    ],
  },
  ch02: {
    left: 'figure',
    pieces: [
      '白厄全篇 2,550 条台词、202 个出场步骤，但和他命定 O09 相关的词极少：「骄阳」全篇只出现 3 次，O09 唯一一次「本人引用」是在 3.4 把名字交出去——「诚如神谕所示……愿这名号能代我同行」（#16719）。3.4 的「台词峰值」也不是戏份，而是身份分裂：白厄 425 + 卡厄斯兰那 224 + 心中的英雄 49 + 盗火行者 8 + 幼年 4。3.5 他一句台词都没有。',
      '万敌的 O03「终有一日，汝将背后负创而死」听起来像被偷袭，但 3.1 他就亲口告诉白厄「记得从背后刺入我的第十节胸椎，那是唯一能杀死我的弱点」（#7211）。兑现出现两次：主线 3.3（#15174）与记忆线 3.4（#17283/#17294）——两代白厄各执行一次。',
      '那刻夏的 O06 有一条全篇唯一的「时间倒置」：兑现事件段（3.2|争辩|2）在文本顺序上早于神谕原句（3.2|学者|4）46 步；瑟希斯念出原句前「至纯粹」已出现两次，神谕一出他当场判定「只是把我过去、现在和未来成就的一切复述了一遍」（#11588）。不是预言决定事件，而是事件发生后被追认为预言。',
    ],
    figures: [
      {
        src: '/figures/f7_bai_trajectory.png',
        title: 'f7 白厄四联图',
        axes: '横轴：版本 3.0–3.7；四个子图纵轴分别是台词条数/出场步骤、形态条数、称呼命中、所在步骤的检测器分数。',
        judge: '台词高 = 这一版是主场；形态里「非本体」条数高 = 身份分裂强；称呼从「老师」转向「伙伴/英雄」= 关系变化；检测器分数高只说明语言突变强，不代表更感人。',
        conclusion: '3.0 台词最多（634 条），但 3.4 才是身份峰值（卡厄斯兰那 224 + 心中的英雄 49），3.5 是 0 条（缺席）。',
      },
    ],
  },
  ch03: {
    left: 'text',
    pieces: [
      '昔涟贯穿 3.0–3.7，2,393 条台词、222 步，语言形态从「迷迷」的断句体走到「讲述者」和「另一位作者」（按设定即她自己）。她最重的一场戏是 3.7 的水晶花寓言：同一个故事被改写了两次——原版里碎片中有一团光「它是『爱』」（#23894–#23896）；昔涟第一次改，说「无瑕」意味着封闭、没有心也不懂爱（#23903–#23913）；终局第二次改，说光在「每一片破碎的水晶映照出的世界里」（#25228–#25231）。三个版本的句向量相似度 0.79–0.87，词频加权只有 0.28–0.47：语义被保住、字面被换掉。',
      '遐蝶的 O04 是 13 条里反转最彻底的一条：判词说「相拥之后，便是永恒的离别」，她先主动认领「那仿佛并非预言，而是我过去的全部写照」（#10091–#10092），兑现时改写「为它写下另一种诠释」（#11467–#11469），3.6 大墓的记忆场景里还补了一句「我还以为缇宁老师的预言出错了呢」（#21860–#21861）。',
      '缇宝的 O02 来源不是泰坦原话：雅努斯说「灵魂必遭歧路分离，碎作千片化身，如琉璃掷地……」（#7939），缇宝把它提炼成十二字箴言（#8049）。角色曲《昔涟》放进同一空间后：14 个角色里最接近昔涟（0.586），昔涟各版本里最接近 3.7（0.615），但神谕最高是 O04（0.484）而不是 O13（0.416）。',
    ],
    figures: [
      {
        src: '/figures/f8_xi_trajectory.png',
        title: 'f8 昔涟四联图',
        axes: '横轴：版本；四个子图纵轴分别是台词量、形态构成、称呼命中、检测器分数。',
        judge: '形态条的「切换点」越清楚，越能说明语言阶段在变；句长/检测器分数上升 = 向「讲述者」过渡。',
        conclusion: '3.0–3.3 几乎全是「迷迷」，3.4 之后切到「记忆形态/往昔的涟漪」，3.7 出现「另一位作者」——三个切换点都能在图上指出来。',
      },
      {
        src: '/figures/f13_crystal_flower_semantic.png',
        title: 'f13 水晶花曲线',
        axes: '横轴：全局步序 1–686；纵轴：与 K36 原文的余弦相似度（词频加权与语义向量两条线）。',
        judge: '峰在 3.7 结尾 = 与「收梢」主题真实重叠（好）；峰恰好落在 K36 自己的步骤 = 参考文本自匹配（坏）。',
        conclusion: '词频加权峰在步序 663（3.7 结尾），不在 K36 步；3.5 闪回区还有一批语义向量假峰。',
      },
    ],
  },
  ch04: {
    left: 'figure',
    pieces: [
      '海瑟音与刻律德菈：O10 属海瑟音、O11 属刻律德菈，两条话用词相同、只换语序。但引用分布极不对称：刻律德菈本人 0 次引用神谕，O11 全篇唯一一次出现是海瑟音替她念的（#20228）。兑现也交换了：刻律德菈死于「天地境界之海，一汪浅浅的死水」（#20339–#20340），「完成征服」却落空（#20353）；海瑟音献出余生的清醒与自由（#19814）。半句交换的动作是刻律德菈亲手完成的：赠送「天地境界之海」（#20322）、交付「天外的大海」（#20354）。',
      '阿格莱雅完成最完整的引用链：「汝将最后一次沐浴……」（#7458）→ 故人之音把「汝」换成「我」（#14241–#14242）→ 结局宣告「我将最后一次沐浴……现在，是时候将其兑现了」（#16615）。赛飞儿的「千年永昼」只是一次时间短语删改（#14400→#14570）；O08 的「分文」就是她的硬币（#10329–#10342），被夺走后她才失速而死（#14558→#14577–#14578）。',
      '列车组：开拓者 3,058 条里 79.5% 是玩家选项，真实对白与短信只有 626 条；三月七 3.1/3.3 零台词（幽灵期）；丹恒 1,541 条含 89 条「丹枫」。所以列车组单列、不与黄金裔比较：他们的主线塑造在翁法罗斯之外。',
    ],
    figures: [
      {
        src: '/figures/f14_mirror_pair_O10_O11.png',
        title: 'f14 镜像曲线（对偶组）',
        axes: '横轴：全局步序；纵轴：与 O10/O11 的余弦相似度。',
        judge: '两条线分离大 = 能区分两条镜像命定（好）；重合 = 分不开（坏）。',
        conclusion: '词频加权逐点重合，语义向量平均差 0.005、最大 0.018 → 两种表示都分不开，归属只能靠引用与兑现判。',
      },
      {
        src: '/figures/f10_coverage.png',
        title: 'f10 覆盖率图',
        axes: '横轴：角色（A 组 11 + B 组 3）；纵轴：出场步骤数 / 被精读覆盖的步骤数。',
        judge: '差额越大 = 数据多但没被细读（坏，提示补读）；覆盖率特别高 = 重点标注集中（好，但可能带系统性偏好）。',
        conclusion: '开拓者 387 步只有 25 步被精读（6.5%），白厄 22/202（10.9%），刻律德菈 32.3% 最高——这正是后来做 14 角色全量精读（L3）的原因。',
      },
    ],
  },
  ch05: {
    left: 'text',
    pieces: [
      '13 条神谕的兑现可分四型：字面 8、反转 2、错位 1，外加「追认」（O06）、「双线」（O03）、「两段」（O13）。「明天见」也不是直线：起于白厄 3.0 的道别（#4211），缇宝第一次说是对商人的客套（#5259），母亲临终那句（#6876）被改写成「世上最伟大的预言」（#8077），最后在 3.7 由群体说出（#25271、#25778、#25779「乘以一千」）。「明天」全库 108 条（剔除 2 条跨词误报），昔涟谈「明天」17 次，却只说 1 次「明天见」——制造明天的人几乎不说那句口号。',
      '水晶花寓言是改写最完整的演示：「水晶花」一词全篇只出现 11 次、全部在 3.7、全部由昔涟说；三版最像的角色都是昔涟（0.58–0.63），最像的神谕却是 O04（0.52–0.54），不是 O13。《如我所书》把这一切收进口袋：名字最早来自昔涟童年的神谕牌册（#15977–#15978），最后成了银河级的记录（#25648）；结尾 14 个名字 vs「十三位英雄」（#26119–#26122 vs #26176）——13 = 11 位黄金裔 + 三月七 + 丹恒。',
      '边界：检索在事件级失效（7/13 可评、最好 MRR 0.132），标注是 LLM 辅助（κ=0.788），相似度不是含义强度——这三条限制和数据本身一样重要。',
    ],
    figures: [
      {
        src: '/figures/f12_mingtian_timeline.png',
        title: 'f12 明天见时间线',
        axes: '横轴：版本 3.0–3.7；纵轴：出现次数。',
        judge: '母题从单版本扩散到多版本、且首尾都有 = 生命周期完整（好）；只集中在某一版本 = 局部用语。',
        conclusion: '3.1 峰 9 次、3.7 5 次，中间零星——「起—收」两端高，符合「客套→预言→共同体誓言」的讲述。',
      },
      {
        src: '/figures/f13_crystal_flower_semantic.png',
        title: 'f13 水晶花曲线',
        axes: '横轴：全局步序；纵轴：与 K36 原文的余弦相似度。',
        judge: '两条线同步上升、且峰在 3.7 结尾 = 主题重叠可信（好）；只有一条线抬、或峰落在 K36 步 = 可疑。',
        conclusion: '词频加权峰在 3.7 结尾，语义向量在 3.5 闪回区有假峰——两条线不同步，说明「相似」来源不同。',
      },
      {
        src: '/figures/f15_retrieval_v3.png',
        title: 'f15 检索对比（边界）',
        axes: '横轴：检索方法；纵轴：MRR（同组内越高越好，跨组不可比）。',
        judge: '同组 MRR 越高越好；v3 组全部 <0.15 = 方法失败（这是结论，不是排名）。',
        conclusion: 'v3 组最好 0.132，对照组 0.48——对照组「更好」但 gold 不同、池里有干扰，不能直接说词面方法更好。',
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
    <div className="key-grid">
      {rows.map(([k, v]) => (
        <div className="key-item" key={k}>
          <span className="key-label">{k}</span>
          <span className="key-value">{v}</span>
        </div>
      ))}
    </div>
  );
}

function FigureCard({ fig }) {
  return (
    <figure className="figure-card">
      <img src={fig.src} alt={fig.title} loading="lazy" />
      <figcaption>
        <strong>{fig.title}</strong>
        <p><em>轴</em>：{fig.axes}</p>
        <p><em>怎么判好坏</em>：{fig.judge}</p>
        <p><em>本图结论</em>：{fig.conclusion}</p>
      </figcaption>
    </figure>
  );
}

const CHARACTER_FIGS = {
  ch02: [
    { name: '白厄', img: '/figures/chars/白厄_mini.png', note: '沉默：几乎不引用自己的命定；3.4 身份分裂峰值' },
    { name: '万敌', img: '/figures/chars/万敌_mini.png', note: '递刀：3.1 交出弱点，两次兑现各一次' },
    { name: '那刻夏', img: '/figures/chars/那刻夏_mini.png', note: '追认：兑现比神谕原句早 46 步' },
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
  ],
};

function Section({ ch, data }) {
  const c = CONTENT[ch.id] || {};
  const chars = CHARACTER_FIGS[ch.id] || [];
  return (
    <section id={ch.id} className="chapter">
      <header className="chapter-head">
        <span className="chapter-num">第 {ch.num} 章</span>
        <h2>{ch.title}</h2>
        <p className="kicker">{ch.kicker}</p>
      </header>
      <div className="prose">
        {c.pieces?.map((p, i) => <p key={i}>{p}</p>)}
      </div>
      {chars.length > 0 && (
        <div className="char-block">
          <h3 className="block-title">角色数据卡（每人一张，轴与结论写在图下）</h3>
          <div className="char-grid">
            {chars.map((x) => (
              <figure className="char-card" key={x.name}>
                <img src={x.img} alt={`${x.name} 迷你图`} loading="lazy" />
                <figcaption>
                  <strong>{x.name}</strong>
                  <p>{x.note}</p>
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      )}
      {(c.figures || []).length > 0 && (
        <div className="figure-block">
          <h3 className="block-title">关键图（轴 / 怎么判好坏 / 本图结论）</h3>
          <div className="figure-grid">
            {(c.figures || []).map((f) => <FigureCard fig={f} key={f.src + f.title} />)}
          </div>
        </div>
      )}
      <KeyNumbers data={data} />
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
          <p className="lede">神谕、引用与兑现：26,332 条台词里，「命定」是一套可以被测量、被接管、被改写的语言实践。</p>
          <div className="meta-chips">
            <span>26,332 条台词</span><span>13 条神谕</span><span>14 个角色全量精读</span><span>6 章 · 每图旁标轴</span>
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
