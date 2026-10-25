import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDown, ChevronDown, Database, FileText, Search, AlertTriangle } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from 'recharts';
import { Badge, Button, Card, CardContent, CardHeader, CardTitle } from './components/ui.jsx';

const DATA = '/data/';
const curveCharacters = ['阿格莱雅','白厄','丹恒','风堇','海瑟音','开拓者','刻律德菈','那刻夏','赛飞儿','三月七','缇宝','万敌','昔涟','遐蝶'];
const curveVersions = ['3.0','3.1','3.2','3.3','3.4','3.5','3.6','3.7'];
const CURVE_POINT_GAP = 24;
const CURVE_LEFT_PAD = 18;
const CURVE_RIGHT_PAD = 18;
const num = value => Number.isFinite(Number(value)) ? Number(value) : 0;
const numeric = value => value === '' || value === null || value === undefined || !Number.isFinite(Number(value)) ? null : Number(value);
const formatMetric = value => value === null || value === undefined || Number.isNaN(Number(value)) ? '缺失' : Number(value).toFixed(3);
async function loadJSON(name) { const response = await fetch(DATA + name); if (!response.ok) throw new Error(`${name}: ${response.status}`); return response.json(); }
async function loadCSV(name) { const response = await fetch(DATA + name); if (!response.ok) throw new Error(`${name}: ${response.status}`); const text = await response.text(); const rows = []; let row = [], cell = '', quoted = false; for (let i = 0; i < text.length; i += 1) { const c = text[i], next = text[i + 1]; if (c === '"' && quoted && next === '"') { cell += '"'; i += 1; continue; } if (c === '"') { quoted = !quoted; continue; } if (c === ',' && !quoted) { row.push(cell); cell = ''; continue; } if ((c === '\n' || c === '\r') && !quoted) { if (c === '\r' && next === '\n') i += 1; row.push(cell); if (row.some(Boolean)) rows.push(row); row = []; cell = ''; continue; } cell += c; } if (cell || row.length) { row.push(cell); rows.push(row); } const header = rows.shift() || []; return rows.map(r => Object.fromEntries(header.map((h, i) => [h, r[i] ?? '']))); }
async function loadJSONL(name) { const response = await fetch(DATA + name); if (!response.ok) throw new Error(`${name}: ${response.status}`); const text = await response.text(); return text.split(/\r?\n/).filter(Boolean).map(line => JSON.parse(line)); }
function useResource(loader, name) { const [state, setState] = useState({data: null, error: null}); useEffect(() => { let live = true; loader(name).then(data => live && setState({data, error: null})).catch(error => live && setState({data: null, error})); return () => { live = false; }; }, [loader, name]); return state; }
function ResourceState({error, loading='正在读取数据…'}) { if (error) return <p className="resource-error"><AlertTriangle size={15}/> {error.message}</p>; return <p className="muted">{loading}</p>; }
function Figure({children, caption, dataFile}) { return <div className="report-figure"><div className="figure-body">{children}</div><div className="figure-caption">{caption}{dataFile && <span className="figure-source">数据：{dataFile}</span>}</div></div>; }
function Method({number, title, question, principle, why, output, limit}) { return <Card className="method-card"><CardHeader><Badge>方法 {number}</Badge><CardTitle className="mt-3 text-2xl">{title}</CardTitle></CardHeader><CardContent><div className="method-grid"><div><b>它解决什么问题</b><p>{question}</p></div><div><b>原理</b><p>{principle}</p></div><div><b>为什么用</b><p>{why}</p></div><div><b>处理后变成什么</b><p>{output}</p></div></div><p className="method-limit"><b>边界：</b>{limit}</p></CardContent></Card>; }
function DataTrace({file, rows=[], columns, children}) { const [query, setQuery] = useState(''); const visible = rows.filter(row => !query || Object.values(row).join(' ').toLowerCase().includes(query.toLowerCase())).slice(0, 120); const heads = columns || (rows[0] ? Object.keys(rows[0]) : []); return <details className="data-trace"><summary><Database size={15}/>查看原始数据（{file}，{rows.length || '快照'} 行）<ChevronDown size={15}/></summary>{children && <p>{children}</p>}{rows.length > 0 && <><div className="detail-tools"><span>最多展示前 120 行</span><input value={query} onChange={e => setQuery(e.target.value)} placeholder="筛选字段或文本"/></div><div className="table-scroll"><table><thead><tr>{heads.map(h => <th key={h}>{h}</th>)}</tr></thead><tbody>{visible.map((row, i) => <tr key={i}>{heads.map(h => <td key={h} title={String(row[h] ?? '')}>{String(row[h] ?? '')}</td>)}</tr>)}</tbody></table></div></>}</details>; }
function MarkerShape({cx, cy, payload, onEnter, onLeave}) {
  if (!payload || !Number.isFinite(cx) || !Number.isFinite(cy)) return null;
  const color = payload.markerColor;
  const events = {onMouseEnter: event => { const shell = event.currentTarget.closest('.curve-chart-shell')?.getBoundingClientRect(); onEnter?.(payload, shell ? event.clientX - shell.left : cx, shell ? event.clientY - shell.top : cy); }, onMouseLeave: () => onLeave?.(), style: {cursor: 'pointer'}};
  const hit = <circle cx={cx} cy={cy} r={10} fill="transparent" stroke="transparent" pointerEvents="all"/>;
  if (payload.markerLabel === '兑现') return <g {...events}>{hit}<path d={`M ${cx} ${cy - 7} L ${cx + 2} ${cy - 2} L ${cx + 7} ${cy - 2} L ${cx + 3} ${cy + 1} L ${cx + 5} ${cy + 7} L ${cx} ${cy + 3} L ${cx - 5} ${cy + 7} L ${cx - 3} ${cy + 1} L ${cx - 7} ${cy - 2} L ${cx - 2} ${cy - 2} Z`} fill={color} stroke="#fff" strokeWidth="1"/></g>;
  if (payload.markerLabel === '意义转折') return <g {...events}>{hit}<rect x={cx - 4} y={cy - 4} width="8" height="8" transform={`rotate(45 ${cx} ${cy})`} fill={color} stroke="#fff" strokeWidth="1"/></g>;
  if (payload.markerLabel === '关键事件') return <g {...events}>{hit}<rect x={cx - 4} y={cy - 4} width="8" height="8" fill={color} stroke="#fff" strokeWidth="1"/></g>;
  return <g {...events}>{hit}<path d={`M ${cx} ${cy - 6} L ${cx + 6} ${cy + 5} L ${cx - 6} ${cy + 5} Z`} fill={color} stroke="#fff" strokeWidth="1"/></g>;
}

function CurvePoint({cx, cy, payload, valueKey, series, color, onEnter, onLeave}) {
  if (!payload || !Number.isFinite(cx) || !Number.isFinite(cy) || payload[valueKey] == null) return null;
  const events = {onMouseEnter: event => { const shell = event.currentTarget.closest('.curve-chart-shell')?.getBoundingClientRect(); onEnter?.({row: payload, value: payload[valueKey], series, color, cx: shell ? event.clientX - shell.left : cx, cy: shell ? event.clientY - shell.top : cy}); }, onMouseLeave: () => onLeave?.(), style: {cursor: 'crosshair'}};
  return <g {...events}><circle cx={cx} cy={cy} r={3} fill={color} stroke="#fff" strokeWidth="1"/><circle cx={cx} cy={cy} r={8} fill="transparent" stroke="transparent" pointerEvents="all"/></g>;
}

function FullRoleCurve({character}) {
  const {data: rows, error} = useResource(loadCSV, `oracle_sim__${character}.csv`);
  const fulfillment = useResource(loadJSON, 'oracle-fulfillment.v2.json');
  const keyEvents = useResource(loadJSON, 'key-events.json');
  const knifeScenes = useResource(loadJSON, 'knife-scenes.json');
  const normalized = useMemo(() => {
    const sorted = (rows || []).map(x => ({
      ...x,
      order: num(x.order),
      step: num(x.step_idx),
      tf: numeric(x.tfidf_own),
      tfr: numeric(x.tfidf_roll5),
      sb: numeric(x.sbert_own),
      sbr: numeric(x.sbert_roll5),
      first: num(x.in_oracle_first) === 1,
      recitation: num(x.in_recitation) === 1,
      fulfillment: num(x.in_fulfillment) === 1,
      meaningTurn: num(x.in_meaning_turn) === 1,
      keyEvent: num(x.in_key_event) === 1,
      knife: num(x.in_knife) === 1,
    })).sort((a, b) => a.order - b.order || a.step - b.step);
    const counts = new Map();
    sorted.forEach(row => counts.set(row.order, (counts.get(row.order) || 0) + 1));
    const seen = new Map();
    return sorted.map((row, rowIndex) => {
      const index = seen.get(row.order) || 0;
      seen.set(row.order, index + 1);
      // Keep the global order as the integer tick, while spreading steps inside
      // the interval before the next order so duplicate orders remain readable.
      return {...row, plotX: row.order + (index + 1) / (counts.get(row.order) + 1), canvasX: CURVE_LEFT_PAD + rowIndex * CURVE_POINT_GAP};
    });
  }, [rows]);
  const [eventHover, setEventHover] = useState(null);
  const [curveHover, setCurveHover] = useState(null);
  const [windowRange, setWindowRange] = useState({startIndex: 0, endIndex: 0});
  const plotViewportRef = useRef(null);
  const windowSize = Math.max(1, Math.min(40, normalized.length));
  const maxWindowStart = Math.max(0, normalized.length - windowSize);
  const defaultWindowEnd = windowSize - 1;
  useEffect(() => {
    setWindowRange({startIndex: 0, endIndex: defaultWindowEnd});
    setEventHover(null);
    setCurveHover(null);
  }, [character, defaultWindowEnd]);
  useEffect(() => {
    if (plotViewportRef.current) plotViewportRef.current.scrollLeft = windowRange.startIndex * CURVE_POINT_GAP;
  }, [character, windowRange.startIndex, normalized.length]);
  if (!rows || !fulfillment.data || !keyEvents.data || !knifeScenes.data) return <ResourceState error={error || fulfillment.error || keyEvents.error || knifeScenes.error} loading={`正在读取 ${character} 曲线及事件证据…`}/>;
  const globalBounds = {'3.0': 1, '3.1': 11, '3.2': 20, '3.3': 30, '3.4': 39, '3.5': 45, '3.6': 52, '3.7': 61};
  const minOrder = normalized[0]?.order ?? 1;
  const maxOrder = normalized[normalized.length - 1]?.order ?? 1;
  const plotMaxX = normalized[normalized.length - 1]?.canvasX ?? CURVE_LEFT_PAD;
  const plotDomain = [0, plotMaxX + CURVE_RIGHT_PAD];
  const canvasWidth = Math.max(960, plotDomain[1]);
  const starts = Object.entries(globalBounds).filter(([, order]) => order >= minOrder && order <= maxOrder);
  const orderX = order => normalized.find(row => row.order === order)?.canvasX;
  const tickValues = starts.map(([, order]) => orderX(order)).filter(value => value !== undefined);
  const tickLabels = new Map(starts.map(([version, order]) => [orderX(order), version]));
  const tfValues = normalized.map(row => row.tf).filter(value => value !== null);
  const tfMin = Math.min(...tfValues, 0);
  const tfMax = Math.max(...tfValues, 0);
  const tfPad = (tfMax - tfMin) * 0.15 + 0.01;
  const tfDomain = [tfMin - tfPad, tfMax + tfPad];
  const sbValues = normalized.map(row => row.sb).filter(value => value !== null);
  const sbMax = Math.max(...sbValues, 0);
  const sbDomain = [0, Math.max(0.8, sbMax + 0.05)];
  const railY = relative => tfDomain[0] + relative * (tfDomain[1] - tfDomain[0]);
  const bySegment = new Map(normalized.map(row => [`${row.version}|${row.task}|${row.step}`, row]));
  const eventRow = (segmentId, label, color, relative) => {
    const row = bySegment.get(segmentId);
    return row ? {...row, markerLabel: label, markerColor: color, markerY: railY(relative), x: row.canvasX, y: railY(relative), eventSegment: segmentId} : null;
  };
  const ownOracleIds = new Set((fulfillment.data.oracles || []).filter(oracle => oracle.holder === character).map(oracle => oracle.oracle_id));
  const oracleEvents = (fulfillment.data.oracles || []).filter(oracle => ownOracleIds.has(oracle.oracle_id)).flatMap(oracle => oracle.event_segments || []);
  const railRows = [
    ...oracleEvents.filter(event => event.role === '兑现').map(event => eventRow(event.segment_id, '兑现', '#c0392b', .97)).filter(Boolean),
    ...oracleEvents.filter(event => event.role !== '兑现').map(event => eventRow(event.segment_id, '意义转折', '#8e44ad', .93)).filter(Boolean),
    ...(keyEvents.data.events || []).map(event => eventRow(event.segment_id, '关键事件', '#7f8c8d', .90)).filter(Boolean),
    ...(knifeScenes.data.scenes || []).filter(scene => String(scene.role || '').includes(character)).flatMap(scene => [...(scene.segment_ids || []), ...(scene.ranges || []).map(range => range.split('#')[0])]).map(segmentId => eventRow(segmentId, '刀子', '#d35400', .83)).filter(Boolean),
  ];
  const recitationOrders = [...new Set(normalized.filter(row => row.recitation).map(row => row.order))];
  const firstOrders = [...new Set(normalized.filter(row => row.first).map(row => row.order))];
  const versionLines = starts.slice(1).map(([version, order]) => {
    const x = orderX(order);
    return x === undefined ? null : <ReferenceLine key={version} x={x} stroke="#77838d" strokeDasharray="4 4" label={{value: version, position:'top', fontSize:10}}/>;
  }).filter(Boolean);
  const firstLines = firstOrders.map(order => {
    const x = orderX(order);
    return x === undefined ? null : <ReferenceLine key={`first-${order}`} x={x} stroke="#2c3e50" strokeWidth={1.4}/>;
  }).filter(Boolean);
  const recitationLines = recitationOrders.map(order => {
    const x = orderX(order);
    return x === undefined ? null : <ReferenceLine key={`recite-${order}`} x={x} stroke="#8e44ad" strokeDasharray="2 3" strokeWidth={1}/>;
  }).filter(Boolean);
  const eventCard = eventHover && <div className="event-hover-card" style={{left: Math.min(eventHover.cx + 12, 980), top: Math.max(eventHover.cy - 20, 8)}}><b>{eventHover.payload.markerLabel}</b><strong>{eventHover.payload.version} · 全局任务 {eventHover.payload.order} · 第 {eventHover.payload.step} 步</strong><span>{eventHover.payload.step_title || eventHover.payload.task}</span><small>{eventHover.payload.task}</small></div>;
  const curveCard = curveHover && <div className="curve-point-card" style={{left: Math.min(curveHover.cx + 12, 980), top: Math.max(curveHover.cy - 24, 8)}}><b>{curveHover.series}</b><strong>{curveHover.row.version} · 全局任务 {curveHover.row.order} · 第 {curveHover.row.step} 步</strong><span>{curveHover.row.step_title || curveHover.row.task}</span><em>{formatMetric(curveHover.value)}</em><small>仅显示当前命中的这一条曲线。</small></div>;
  const point = (valueKey, series, color) => props => <CurvePoint {...props} valueKey={valueKey} series={series} color={color} onEnter={setCurveHover} onLeave={() => setCurveHover(null)}/>;
  const lineHover = (valueKey, series, color) => event => {
    const svg = event.currentTarget.ownerSVGElement;
    const box = svg.getBoundingClientRect();
    const gridLine = svg.querySelector('.recharts-cartesian-grid-horizontal line');
    const left = Number(gridLine?.getAttribute('x1') || 86);
    const right = Number(gridLine?.getAttribute('x2') || (box.width - 58));
    const x = event.clientX - box.left;
    const ratio = Math.max(0, Math.min(1, (x - left) / (right - left)));
    const canvasX = plotDomain[0] + ratio * (plotDomain[1] - plotDomain[0]);
    const row = normalized.reduce((best, candidate) => Math.abs(candidate.canvasX - canvasX) < Math.abs(best.canvasX - canvasX) ? candidate : best, normalized[0]);
    if (row?.[valueKey] == null) return;
    setEventHover(null);
    const shell = event.currentTarget.closest('.curve-chart-shell')?.getBoundingClientRect();
    setCurveHover({row, value: row[valueKey], series, color, cx: shell ? event.clientX - shell.left : x, cy: shell ? event.clientY - shell.top : event.clientY - box.top});
  };
  const axisData = [{canvasX: 0, tf: tfDomain[0], sb: sbDomain[0]}];
  const handlePlotScroll = event => {
    const nextStart = Math.max(0, Math.min(maxWindowStart, Math.round(event.currentTarget.scrollLeft / CURVE_POINT_GAP)));
    if (nextStart !== windowRange.startIndex) {
      setWindowRange({startIndex: nextStart, endIndex: Math.min(normalized.length - 1, nextStart + windowSize - 1)});
      setEventHover(null);
      setCurveHover(null);
    }
  };
  return (
    <div className="full-role-curve">
      <div className="curve-legend">
        <Badge className="tf-legend">TF-IDF 原始 / 滚动均值</Badge>
        <Badge className="sb-legend">SBERT 原始 / 滚动均值</Badge>
        <Badge>吟诵：紫色竖线 · 首现：深色竖线</Badge>
        <Badge>兑现：星 · 意义转折：菱形 · 关键事件：方块 · 刀子：三角</Badge>
        <Badge>悬停曲线上的点或事件标记查看单项数据</Badge>
        <Badge>窗口：40 步；拖动底部横向滑块</Badge>
      </div>
      <div className="curve-scroll">
        <div className="curve-chart-shell">
          <div className="curve-chart-frame">
            <div className="curve-axis-pane curve-axis-left">
              <ResponsiveContainer width="100%" height={450}>
                <LineChart data={axisData} margin={{top: 28, right: 0, left: 0, bottom: 64}}>
                  <XAxis type="number" dataKey="canvasX" domain={plotDomain} hide/>
                  <YAxis yAxisId="tf" width={44} domain={tfDomain} tick={{fontSize: 10}} stroke="#1f4e79"/>
                  <Line yAxisId="tf" dataKey="tf" stroke="transparent" dot={false} isAnimationActive={false}/>
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="curve-plot-viewport" ref={plotViewportRef} onScroll={handlePlotScroll}>
              <div className="curve-plot-canvas" style={{width: canvasWidth}}>
                <ResponsiveContainer width="100%" height={450}>
                  <LineChart data={normalized} margin={{top: 28, right: 0, left: 0, bottom: 64}}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#d9e0e4"/>
                    <XAxis type="number" dataKey="canvasX" domain={plotDomain} ticks={tickValues} tickFormatter={value => tickLabels.get(Number(value)) || ''} tick={{fontSize: 11}} label={{value:'全局剧情顺序（同一 order 按步骤展开）', position:'insideBottom', offset:-20}}/>
                    <YAxis yAxisId="tf" width={0} domain={tfDomain} hide/>
                    <YAxis yAxisId="sb" orientation="right" width={0} domain={sbDomain} hide/>
                    {versionLines}{firstLines}{recitationLines}
                    <Line yAxisId="tf" dataKey="tf" name="TF-IDF 当前点" stroke="#1f4e79" connectNulls={false} dot={point('tf','TF-IDF 当前点','#1f4e79')} activeDot={false} isAnimationActive={false} strokeWidth={2} onMouseMove={lineHover('tf','TF-IDF 当前点','#1f4e79')} onMouseLeave={() => setCurveHover(null)}/>
                    <Line yAxisId="tf" dataKey="tfr" name="TF-IDF 滚动均值" stroke="#7f9fbc" connectNulls={false} dot={point('tfr','TF-IDF 滚动均值','#7f9fbc')} activeDot={false} isAnimationActive={false} strokeWidth={1.5} onMouseMove={lineHover('tfr','TF-IDF 滚动均值','#7f9fbc')} onMouseLeave={() => setCurveHover(null)}/>
                    <Line yAxisId="sb" dataKey="sb" name="SBERT 当前点" stroke="#b9530f" connectNulls={false} dot={point('sb','SBERT 当前点','#b9530f')} activeDot={false} isAnimationActive={false} strokeWidth={2} onMouseMove={lineHover('sb','SBERT 当前点','#b9530f')} onMouseLeave={() => setCurveHover(null)}/>
                    <Line yAxisId="sb" dataKey="sbr" name="SBERT 滚动均值" stroke="#d99058" connectNulls={false} dot={point('sbr','SBERT 滚动均值','#d99058')} activeDot={false} isAnimationActive={false} strokeWidth={1.5} onMouseMove={lineHover('sbr','SBERT 滚动均值','#d99058')} onMouseLeave={() => setCurveHover(null)}/>
                    <Scatter yAxisId="tf" data={railRows} dataKey="y" xAxisId={0} shape={props => <MarkerShape {...props} onEnter={(payload, cx, cy) => {setCurveHover(null); setEventHover({payload, cx, cy});}} onLeave={() => setEventHover(null)}/>} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="curve-axis-pane curve-axis-right">
              <ResponsiveContainer width="100%" height={450}>
                <LineChart data={axisData} margin={{top: 28, right: 0, left: 0, bottom: 64}}>
                  <XAxis type="number" dataKey="canvasX" domain={plotDomain} hide/>
                  <YAxis yAxisId="sb" orientation="right" width={44} domain={sbDomain} tick={{fontSize: 10}} stroke="#b9530f"/>
                  <Line yAxisId="sb" dataKey="sb" stroke="transparent" dot={false} isAnimationActive={false}/>
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
          {eventCard}{curveCard}
        </div>
        <div className="curve-window-control">
          <span>步骤窗口：{windowRange.startIndex + 1}–{Math.min(windowRange.endIndex + 1, normalized.length)} / {normalized.length}</span>
          <input type="range" min="0" max={maxWindowStart} step="1" value={windowRange.startIndex} onChange={event => { const nextStart = Number(event.target.value); setWindowRange({startIndex: nextStart, endIndex: Math.min(normalized.length - 1, nextStart + windowSize - 1)}); if (plotViewportRef.current) plotViewportRef.current.scrollLeft = nextStart * CURVE_POINT_GAP; setEventHover(null); setCurveHover(null); }} aria-label="移动 40 步曲线窗口"/>
        </div>
      </div>
      <p className="curve-instruction">事件标记独立于四条曲线，沿用绘图脚本的顶部事件轨；所有点按全量数据的固定画布坐标绘制，窗口只负责移动视野，左右 Y 轴固定。</p>
      <DataTrace file={`oracle_sim__${character}.csv`} rows={normalized} columns={['order','step','version','task','step_title','n_lines','tfidf_own','tfidf_roll5','sbert_own','sbert_roll5','dominant_form','in_oracle_first','in_recitation','in_fulfillment','in_meaning_turn','in_key_event','in_knife']}/>
    </div>
  );
}

const pipeline = [['01','把网页剧情变成记录','输入是 3.0–3.7 主线的 26,332 条台词、旁白和选项。先保留版本、任务、步骤、说话人和顺序，输出逐条 JSONL 与 723 个步骤。','没有位置，后面找到一句神谕时就无法判断它是原文、转述还是兑现。'],['02','把“谁在说话”统一起来','用别名词典把本名、称号和形态映射到规范角色，同时保留原称呼。','同一角色换名字后仍可追踪；换名本身也能成为身份变化的证据。'],['03','把神谕变成可追踪对象','用固定句式、注音对照和人工核对建立 13 条神谕、34 处引用，并区分原文出现、转述、认领、宣告和改写。','研究对象不再是散落关键词，而是一条从原句到兑现的语言履历。'],['04','把文字变成可计算表示','TF-IDF/BM25 记录词面接近程度，句向量记录语义方向；A/B1 再把结构信号加入候选排序。','这些分数用于定位候选，最终仍要回到上下文解释。'],['05','把分数放回剧情','L3 精读和 30 个关键事件把“之前如何理解→发生什么→之后变成什么”写成证据链。','最终输出是可回到数据行的剧情解释，而不是一个分数。']];
function PipelineExample() { return <Card className="pipeline-example"><CardHeader><Badge>一个真实的处理链</Badge><CardTitle>同一段剧情，经过四次转换后仍能回到原文</CardTitle></CardHeader><CardContent><div className="example-grid"><div><span>输入：步骤记录</span><b>3.7 · 晨曦啊，再抚映遥远地平 · 第 4 步</b><p>“这样一来，它就不再是『昔涟』一个人的回忆。”</p></div><div><span>结构化字段</span><b>686 个候选步骤之一</b><p>保留版本、任务、步骤标题、记录数、说话人、顺序和 segment_id。</p></div><div><span>NLP 表示与排序</span><b>A 448 → B1 355</b><p>语义突变 raw=0.812，母题回收 raw=0.591；这些特征改变了候选顺序，但不等于含义分数。</p></div><div><span>人工解释</span><b>回忆的归属发生变化</b><p>“回忆不再属于一个人”改变了记忆的归属；这个含义来自前后文和事件关系。</p></div></div><DataTrace file="baseline-b-scores.json" rows={[{segment_id:'3.7|晨曦啊，再抚映遥远地平|4',step_title:'让回忆不再只属于昔涟',a_rank:448,b1_rank:355,semantic_shift_raw:0.811853,motif_return_raw:0.590523,excerpt:'这样一来，它就不再是『昔涟』一个人的回忆。'}]} columns={['segment_id','step_title','a_rank','b1_rank','semantic_shift_raw','motif_return_raw','excerpt']}/></CardContent></Card>; }
function Pipeline() { return <section className="section"><div className="section-heading"><span className="eyebrow">第一章 · 数据与方法</span><h2>先看一条文本怎样变成一个可复核的判断</h2><p>每一步都回答：输入是什么，做了什么，输出是什么，哪里不能过度解释。</p></div><div className="pipeline-story">{pipeline.map(([n,title,output,why], i) => <div className="pipeline-step" key={n}><div className="step-no">{n}</div><div><h3>{title}</h3><p>{output}</p><p className="why"><b>为什么：</b>{why}</p></div>{i < pipeline.length - 1 && <ArrowDown className="step-arrow" size={18}/>}</div>)}</div><div className="method-stack"><Method number="1" title="结构化抽取" question="如何让每句台词回到剧情位置？" principle="把网页标题、角色标签和正文解析成记录，再按任务和步骤聚合。" why="神谕、角色和事件都依赖顺序和上下文。" output="26,332 条记录、723 个步骤、686 个主分析候选。" limit="字段正确不等于已经理解剧情。"/><Method number="2" title="TF-IDF 与 BM25" question="哪些片段在词面上和神谕接近？" principle="词面方法按词频、稀有度和文本长度计算检索相关性。" why="结果透明，可以指出‘像’来自哪些词。" output="词权重和检索排序。" limit="词面接近不等于同一含义。"/><Method number="3" title="句向量与余弦相似度" question="文字不重复原词时，模型能否找到方向相近的片段？" principle="每段文字被映射为共享的 512 维向量，再比较向量方向。" why="可以观察没有重复神谕词、但可能表达相近关系的片段。" output="角色曲线、神谕相似度和语义突变特征。" limit="模型只报告接近程度，不知道谁改变了谁的命运。"/><Method number="4" title="A / B1 叙事显著性排序" question="结构信息能否补回词面基线漏掉的转折？" principle="A 看词面与局部情绪；B1 加入身份、母题、位置和状态变化。" why="比较结构证据是否能定位‘词不强、含义重’的片段。" output="候选排名、对照指标和失败案例。" limit="B1 仍受步骤长度影响，是入口排序器，不是文学裁判。"/></div><PipelineExample/></section>; }
function OracleStory() { const {data, error} = useResource(loadJSON, 'oracle-fulfillment.v2.json'); const citation = useResource(loadJSON, 'oracle-citation-coding.json'); const [query, setQuery] = useState(''); if (!data || !citation.data) return <section className="section chapter-tint"><ResourceState error={error || citation.error} loading="正在读取神谕履历…"/></section>; const occurrences = citation.data.occurrences || []; const filtered = data.oracles.filter(o => `${o.holder}${o.text}${o.titan}`.includes(query)); return <section id="oracle" className="section chapter-tint"><div className="section-heading"><span className="eyebrow">第二章 · 神谕的文本生命周期</span><h2>同一句话在不同说话人手里，承担不同的动作</h2><p>先看白厄的“被转述 → 被交出 → 被揭示为书写”，再把 13 条神谕逐条展开。引用证据保留到任务、步骤和记录号。</p></div><Card className="thesis-card"><CardContent><p className="quote">“汝将肩负骄阳，直至灰白的黎明显著。”</p><p>3.0 是旁白转述，3.4 白厄把“救世主”的名号交给开拓者，3.7 昔涟揭示这句话是她写给白厄的希望。词面没有变，语言的归属和行动变了。</p></CardContent></Card><div className="oracle-toolbar"><h3>13 条神谕履历</h3><div className="search-box"><Search size={16}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索持有者、泰坦或原文"/></div></div><div className="oracle-list">{filtered.map((oracle, index) => { const cites = occurrences.filter(x => x.oracle_id === oracle.oracle_id); return <details className="oracle-card" key={oracle.oracle_id} open={index === 0}><summary><div><h3>{oracle.holder}</h3><p>{oracle.titan}</p></div><ChevronDown size={17}/></summary><p className="oracle-text">{oracle.text}</p><div className="tags"><Badge>{oracle.current_filled_type || '待核对'}</Badge><Badge>{cites.length} 次引用</Badge>{oracle.event_segments?.length > 0 && <Badge>{oracle.event_segments.length} 个兑现段</Badge>}</div>{(oracle.event_segments?.length > 0 || oracle.sequence_note || oracle.note) && <div className="fulfillment-evidence"><b>兑现证据</b>{oracle.event_segments?.map(event => <span key={event.segment_id || event}>{event.segment_id || event} · {event.role || oracle.current_filled_type || '兑现'}</span>)}{oracle.sequence_note && <p>顺序说明：{oracle.sequence_note}</p>}{oracle.note && <p>口径说明：{oracle.note}</p>}</div>}<div className="citation-line">{cites.map((cite, i) => <span key={`${cite.record_id}-${i}`} title={`${cite.version} · ${cite.stage}`} style={{left: `${cites.length === 1 ? 50 : i / (cites.length - 1) * 100}%`}}/> )}</div><div className="citation-ledger">{cites.map(cite => <div className="citation-entry" key={cite.record_id}><div><Badge>{cite.stage}</Badge><b>{cite.version} · {cite.task} · 第 {cite.step_idx} 步</b></div><p>{cite.text}</p><small>record_id {cite.record_id} · {cite.speaker || '旁白'} · {cite.citation_form || '未分类'}</small></div>)}</div><DataTrace file="oracle-citation-coding.json" rows={cites} columns={['oracle_id','record_id','version','task','step_title','speaker','stage','citation_form','text']}/></details>; })}</div></section>; }
function StepEvidence() { const {data: steps, error} = useResource(loadJSONL, 'segments.jsonl'); const [query, setQuery] = useState(''); const [selectedId, setSelectedId] = useState('3.7|晨曦啊，再抚映遥远地平|4'); if (!steps) return <Card><CardContent><ResourceState error={error} loading="正在读取 723 个步骤…"/></CardContent></Card>; const filtered = steps.filter(step => `${step.segment_id}${step.task}${step.step_title}${step.text_dialogue}`.includes(query)); const selected = steps.find(step => step.segment_id === selectedId) || filtered[0] || steps[0]; return <Card className="step-evidence"><CardHeader><CardTitle>步骤级证据浏览器</CardTitle><p className="muted">步骤是排序和曲线的单位；展开后继续查看其中按原顺序保存的记录。</p><div className="search-box"><Search size={16}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索任务、步骤或文本"/></div></CardHeader><CardContent><div className="step-browser"><div className="step-list">{filtered.slice(0, 80).map(step => <button className={selected?.segment_id === step.segment_id ? 'step-list-item active' : 'step-list-item'} key={step.segment_id} onClick={() => setSelectedId(step.segment_id)}><b>{step.version} · {step.step_title}</b><small>{step.task} · {step.n_main} 条主记录</small></button>)}</div>{selected && <div className="step-detail"><div className="step-detail-head"><Badge>{selected.segment_id}</Badge><h3>{selected.step_title}</h3><p>{selected.task}</p></div><div className="step-fields"><span>主记录 {selected.n_main}</span><span>对白 {selected.n_dialogue}</span><span>旁白 {selected.n_narration}</span><span>选项 {selected.n_option}</span><span>字符数 {selected.char_len}</span></div><div className="record-list">{(selected.main_records || []).slice(0, 24).map(record => <div className="record-row" key={record.id}><small>#{record.id} · {record.speaker || '旁白'} · {record.kind}</small><p>{record.text}</p></div>)}</div><DataTrace file="segments.jsonl" rows={[selected]} columns={['segment_id','version','order','task','step_idx','step_title','n_records','n_main','n_dialogue','n_narration','char_len','speakers']}/></div>}</div></CardContent></Card>; }
function Evidence() { const events = useResource(loadJSON, 'key-events.json'); const labels = useResource(loadJSON, 'annotation-labels.json'); const [query, setQuery] = useState(''); const eventRows = events.data?.events || []; const labelRows = labels.data?.samples || []; const filteredEvents = eventRows.filter(e => `${e.id}${e.event_name}${e.segment_id}${e.meaning_before}${e.meaning_after}`.includes(query)); return <section id="evidence" className="section evidence-section"><div className="section-heading"><span className="eyebrow">第三章 · 证据层</span><h2>统计只负责把读者带到这里，含义要在前后文里读出来</h2><p>先选一个步骤，再看其中的记录顺序、关键事件和标注。这样每个统计点都有回到文本的路径。</p></div><StepEvidence/><div className="evidence-grid"><Card><CardHeader><CardTitle>30 个关键事件</CardTitle><div className="search-box"><Search size={16}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索事件、角色或步骤"/></div></CardHeader><CardContent><div className="event-list">{filteredEvents.slice(0, 12).map(event => <details className="event-card" key={event.id}><summary><Badge>{event.id}</Badge><b>{event.event_name}</b><span>{event.version} · {event.confidence}</span></summary><p><strong>之前：</strong>{event.meaning_before}</p><p><strong>之后：</strong>{event.meaning_after}</p><p className="quote-small">“{event.evidence_quote}”</p><small>{event.segment_id} · record_id {event.evidence_record_id} · {event.evidence_speaker || '未标注说话人'}</small></details>)}</div><DataTrace file="key-events.json" rows={eventRows} columns={['id','version','segment_id','event_name','confidence','evidence_record_id','evidence_quote']}/></CardContent></Card><Card><CardHeader><CardTitle>74 条显著性标注</CardTitle><p className="muted">稳定性用于说明标注过程，不能当成客观真值。</p></CardHeader><CardContent><div className="label-summary"><strong>等级 0–3</strong><span>0：{labelRows.filter(x => x.significance === 0).length}</span><span>1：{labelRows.filter(x => x.significance === 1).length}</span><span>2：{labelRows.filter(x => x.significance === 2).length}</span><span>3：{labelRows.filter(x => x.significance === 3).length}</span></div><div className="label-list">{labelRows.filter(x => x.significance >= 2).slice(0, 8).map(label => <div className="label-row" key={label.segment_id}><Badge>等级 {label.significance}</Badge><div><b>{label.step_title}</b><p>{label.note}</p><small>{label.segment_id} · {label.types.join('、')}</small></div></div>)}</div><DataTrace file="annotation-labels.json" rows={labelRows} columns={['segment_id','layer','version','task','step_title','significance','types','confidence','note']}/></CardContent></Card></div></section>; }
function RoleAtlas() { const {data: heat, error} = useResource(loadCSV, 'f11_oracle_similarity_heatmap.csv'); const [selected, setSelected] = useState('白厄'); const versions = curveVersions.filter(version => (heat || []).some(x => x.version === version)); const max = key => Math.max(...(heat || []).map(r => num(r[key])), 1e-9); return <section id="role-curves" className="section"><div className="section-heading"><span className="eyebrow">第四章 · 角色轨迹</span><h2>每个角色按自己的出场范围阅读</h2><p>曲线沿用原始绘图脚本：全局 order、全局版本边界和按步骤均值计算。</p></div><div className="role-selector">{curveCharacters.map(character => <Button key={character} className={selected === character ? 'selected' : ''} onClick={() => setSelected(character)}>{character}</Button>)}</div><Card className="atlas-card"><CardHeader><CardTitle>{selected}：与神谕文本的相似度</CardTitle></CardHeader><CardContent><FullRoleCurve key={selected} character={selected}/></CardContent></Card><Card className="atlas-card"><CardHeader><CardTitle>全体角色 × 版本热力图</CardTitle><p className="muted">版本顺序固定为 3.0→3.7；热力图只展示版本内均值，单人图才保留每个出场步骤。</p></CardHeader><CardContent>{!heat ? <ResourceState error={error}/> : <div className="heatmap-grid">{['tfidf_own_mean','sbert_own_mean'].map(key => <div key={key}><h4>{key === 'tfidf_own_mean' ? 'TF-IDF 版本均值' : 'SBERT 版本均值'}</h4><div className="heatmap"><div></div>{versions.map(version => <span key={version}>{version}</span>)}{curveCharacters.map(character => <Fragment key={character}><b>{character}</b>{versions.map(version => { const row = heat.find(x => x.char === character && x.version === version); const value = num(row?.[key]); return <i key={`${character}-${version}`} title={`${character} · ${version} · ${value.toFixed(3)}`} style={{background: `rgba(201,154,72,${.12 + value / max(key) * .82})`}}>{value ? value.toFixed(2) : '—'}</i>; })}</Fragment>)}</div></div>)}</div>}<DataTrace file="f11_oracle_similarity_heatmap.csv" rows={heat || []}/></CardContent></Card></section>; }
function SupplementaryData() { const knife = useResource(loadJSON, 'knife-scenes.json'); const farewell = useResource(loadJSON, 'farewell-similarity.json'); const style = useResource(loadJSON, 'style-compare-results.json'); const baseline = useResource(loadJSON, 'baseline-b-scores.json'); const trajectory = useResource(loadJSON, 'character-trajectory-all.json'); const ranked = (baseline.data?.segments || []).slice().sort((a,b) => num(a.rank) - num(b.rank)).slice(0, 20); const knifeRows = knife.data?.scenes || []; const farewellRows = (farewell.data?.queries || []).map(q => ({character: q.character, ...q.verdict_counts})); const styleRows = Object.entries(style.data?.overall?.features || {}).map(([feature, values]) => ({feature, G1: values.G1?.mean, G2: values.G2?.mean, G3: values.G3?.mean})); return <section id="materials" className="section materials-section"><div className="section-heading"><span className="eyebrow">第五章 · 实验材料</span><h2>把其余产物放回页面，而不是藏在仓库里</h2><p>这些材料是候选发现和验证证据，不直接等于剧情结论；展开追溯区可以查看完整快照。</p></div><div className="materials-grid"><Card><CardHeader><CardTitle>36 个刀子 / 高光场景</CardTitle><p className="muted">用于比较 A/B1 能否找到人工标记的场景。</p></CardHeader><CardContent><div className="material-stat"><strong>{knifeRows.length}</strong><span>场景</span></div><DataTrace file="knife-scenes.json" rows={knifeRows} columns={['id','title','role','intensity','type','confidence','segment_ids','record_span','n_records','char_len','oracles']}/></CardContent></Card><Card><CardHeader><CardTitle>告别回收：60 条人工判定</CardTitle><p className="muted">“是 / 存疑 / 否”是人工判定，不是相似度自动结论。</p></CardHeader><CardContent><div className="material-stat"><strong>{farewell.data?.summary?.verdict_totals?.是 || 0} / {farewell.data?.summary?.verdict_totals?.存疑 || 0} / {farewell.data?.summary?.verdict_totals?.否 || 0}</strong><span>是 / 存疑 / 否</span></div><DataTrace file="farewell-similarity.json" rows={farewellRows} columns={['character','是','存疑','否']}/></CardContent></Card><Card><CardHeader><CardTitle>神谕语体与对白语体</CardTitle><p className="muted">保留 G1 神谕、G2 普通对白、G3 引用三组均值。</p></CardHeader><CardContent><DataTrace file="style-compare-results.json" rows={styleRows} columns={['feature','G1','G2','G3']}/></CardContent></Card><Card><CardHeader><CardTitle>B1 候选排名</CardTitle><p className="muted">完整 686 步分数保留在快照；这里先展示排名靠前的入口。</p></CardHeader><CardContent><DataTrace file="baseline-b-scores.json" rows={ranked} columns={['rank','segment_id','step_title','score','n_dialogue','char_len']}/></CardContent></Card><Card><CardHeader><CardTitle>角色覆盖率</CardTitle><p className="muted">L3 精读、标注和关键事件覆盖率分开看，覆盖低不等于没有分析。</p></CardHeader><CardContent><DataTrace file="character-trajectory-all.json" rows={trajectory.data?.summary_table || []}/></CardContent></Card></div></section>; }
function RetrievalChart() { const {data: rows, error} = useResource(loadCSV, 'f15_retrieval_v3.csv'); const [variant, setVariant] = useState('v3'); const display = (rows || []).filter(row => row.panel === 'mrr' && row.variant === variant).map(row => ({label: row.method, value: num(row.value), n_eval: row.n_eval})); return <Figure dataFile="f15_retrieval_v3.csv" caption="只比较同一 MRR 面板和同一实验版本；v3 因排除吟诵段只有 7 条可评神谕。"><div className="metric-switch">{['v1_old','v2_mask','v3_control','v3'].map(v => <Button key={v} className={variant === v ? 'active' : ''} onClick={() => setVariant(v)}>{v}</Button>)}</div>{!rows ? <ResourceState error={error}/> : <ResponsiveContainer width="100%" height={300}><BarChart data={display} margin={{top:12,right:20,left:4,bottom:48}}><CartesianGrid strokeDasharray="3 3" stroke="#d9e0e4"/><XAxis dataKey="label" interval={0} angle={-25} textAnchor="end" height={60} tick={{fontSize:10}}/><YAxis tick={{fontSize:11}}/><Tooltip formatter={(value, name, item) => [`${Number(value).toFixed(3)} · n=${item.payload.n_eval}`, name]}/><Bar dataKey="value" fill="#547b9e" radius={[4,4,0,0]}/></BarChart></ResponsiveContainer>}</Figure>; }
function FailureCases() { const {data: rows, error} = useResource(loadCSV, 'f6_knife_ranks.csv'); if (!rows) return <ResourceState error={error} loading="正在读取 A/B1 场景排名…"/>; const misses = rows.filter(row => num(row.is_double_miss)).slice(0, 9); return <Card className="diagnostic-card"><CardHeader><CardTitle>一个具体的失败案例</CardTitle><p className="muted">A/B1 都漏掉的场景不是异常噪声，而是方法边界。</p></CardHeader><CardContent><div className="failure-list">{misses.map(row => <div className="failure-row" key={row.scene_id}><Badge>{row.scene_id}</Badge><div><b>{row.role} · 强度 {row.intensity}</b><p>A 排名 {row.best_a} · B1 排名 {row.best_b1} · 场景两边都未进 Top100</p><small>{row.scene_id} 的排名来自场景映射后的最佳步骤。</small></div></div>)}</div><DataTrace file="f6_knife_ranks.csv" rows={rows} columns={['scene_id','role','intensity','n_pool_segments','best_a','best_b1','best_a_minus_b1','is_double_miss']}/></CardContent></Card>; }
function Evaluation() { const {data: baseline} = useResource(loadJSON, 'baseline-b-scores.json'); const {data: b2} = useResource(loadJSON, 'baseline-b2-scores.json'); return <section id="limits" className="section chapter-tint"><div className="section-heading"><span className="eyebrow">第五章 · 方法边界</span><h2>先看漏掉了什么，再谈模型增加了什么</h2><p>检测器能定位候选，不能替代剧情解释。这里把 A、B1、B2 和检索版本放在同一口径下。</p></div><FailureCases/><div className="evaluation-flow"><Card><CardContent><b>A：词面与局部情绪</b><p>适合找到死亡、牺牲、告别等显性词面信号。</p><strong>Spearman 0.4005</strong></CardContent></Card><ArrowDown className="flow-arrow"/><Card><CardContent><b>B1：结构增强</b><p>加入语义突变、身份变化、母题回收和状态变化。</p><strong>Spearman 0.5812 · Top100 13/28</strong></CardContent></Card><ArrowDown className="flow-arrow"/><Card><CardContent><b>B2：短步骤修复</b><p>尝试句级和短步信号，整体反而下降。</p><strong>Spearman 0.5408 · Top100 12/28</strong></CardContent></Card></div><Card className="diagnostic-card"><CardContent><b>为什么不能把 B1 叫作“理解剧情”</b><p>万敌告别仍可能排到 308 名；B1 与对白长度的相关为 0.6831。它是候选入口，真正的含义仍要由关键事件和原文前后文说明。</p>{baseline?.focus_case && <p className="quote-small">结构信号案例：{baseline.focus_case.excerpt}（A 排名 {baseline.focus_case.a_rank} → B1 排名 {baseline.focus_case.b_rank}）</p>}{b2 && <small>B2 与 B1 的 Top100 重合率：{b2.b2_vs_b1.top100_overlap}</small>}</CardContent></Card><RetrievalChart/></section>; }
function CharacterClosure() { return <section id="focus" className="section"><div className="section-heading"><span className="eyebrow">第六章 · 两条主线</span><h2>白厄与昔涟不是两张角色卡，而是同一条命定链的两端</h2><p>先读行动和台词，再用曲线确认它们出现在哪个剧情位置。</p></div><article className="character-story bai-story"><div className="character-title"><span className="portrait bai">白</span><div><h3>白厄：从背负骄阳到交付救世主之名</h3><p>关键动作是承认命定，然后把名号交给开拓者。</p></div></div><div className="story-columns"><div><p>白厄几乎不反复念自己的神谕。真正的接管发生在交付句：他让“救世主”从个人名字变成可以由他人承担的公共称谓。</p><p>因此这里必须同时看引用句、说话人变化、交付动作和 3.7 昔涟的揭示，任何一条相似度曲线都不能单独代替这条证据链。</p></div><FullRoleCurve character="白厄"/></div></article><article className="character-story xi-story"><div className="character-title"><span className="portrait xi">昔</span><div><h3>昔涟：从被讲述者到讲述者</h3><p>关键变化是“收梢”成为新的开始。</p></div></div><div className="story-columns"><div><p>昔涟的冲击点不是一句强烈的死亡宣告，而是记忆、讲述者与听众、水晶花寓言和德谬歌诞生同时回收。</p><p>这也是 B1 能补回的片段：词面情绪不强，但身份、记忆和前文解释在同一步里发生了持续变化。</p></div><FullRoleCurve character="昔涟"/></div></article><div className="closure-card"><h3>闭环</h3><p>白厄把“救世主”交给开拓者，昔涟把“神谕”写成新的故事。命定不是模型预测出的标签，而是从引用关系、角色行动和意义回收中被读出来的变化。</p></div></section>; }
function App() { return <><header className="hero"><div className="hero-image"/><div className="hero-copy"><span className="eyebrow">翁法罗斯主线 · 3.0—3.7 · NLP 课程报告</span><h1>命定如何被写进语言</h1><p>从一条台词开始，看它如何被定位、比较、引用，再回到角色和剧情。</p><Button className="hero-button" onClick={() => document.querySelector('#pipeline')?.scrollIntoView()}>开始阅读 <ArrowDown size={16}/></Button></div></header><nav className="topnav"><a href="#pipeline">数据与方法</a><a href="#oracle">神谕履历</a><a href="#evidence">证据层</a><a href="#role-curves">角色轨迹</a><a href="#materials">实验材料</a><a href="#focus">重点分析</a><a href="#limits">方法边界</a></nav><main><section className="section intro"><div><span className="eyebrow">研究问题</span><h2>我们不是预测剧情，而是追踪“命定”如何改变含义。</h2></div><p>26,332 条记录、723 个步骤、13 条神谕、34 次引用、30 个关键事件，最后都要回到角色、行动和原文上下文。</p></section><div id="pipeline"><Pipeline/></div><OracleStory/><Evidence/><RoleAtlas/><SupplementaryData/><CharacterClosure/><Evaluation/></main><footer><FileText size={15}/> 数据快照来自 frontend/public/data；每个图表和证据区都保留对应文件名。</footer></>; }
export default App;
