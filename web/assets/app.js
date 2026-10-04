const $ = (id) => document.getElementById(id);
const labels = {not_started:'未开始',in_progress:'进行中',implemented_unverified:'实现完成待验证',done:'已完成',pending_confirmation:'待确认'};
const dimensionNames = {story:'剧情',art:'美术与场景',system:'系统',polish:'打磨'};
const colors = {overall:'#29382e',story:'#52694d',art:'#9b6945',system:'#4f6f85',polish:'#986372'};
const seriesNames = {overall:'整体',...dimensionNames};
let current, history;
const activeSeries = new Set(Object.keys(seriesNames));

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function pct(value) { return value === null ? '待完善' : `${Math.round(value)}%`; }
function signed(value) { return `${value >= 0 ? '+' : '−'}${Math.abs(value).toFixed(1)}`; }
function dateLabel(value, short = false) {
  if (!value) return '尚未公开发布 · 本地预览';
  return new Intl.DateTimeFormat('zh-CN', {timeZone:'America/New_York',year:short?undefined:'numeric',month:'2-digit',day:'2-digit',hour:short?undefined:'2-digit',minute:short?undefined:'2-digit',hour12:false}).format(new Date(value));
}
function pill(status) { return el('span', labels[status || 'pending_confirmation'], `status-pill ${status || 'pending_confirmation'}`); }
function meter(value, label) {
  const bar = el('div',undefined,`meter${value===null?' unknown':''}`);
  if(value===null){bar.setAttribute('role','img');bar.setAttribute('aria-label',`${label}，评估待完善`);}
  else {
    bar.setAttribute('role','progressbar');bar.setAttribute('aria-label',label);
    bar.setAttribute('aria-valuemin','0');bar.setAttribute('aria-valuemax','100');bar.setAttribute('aria-valuenow',String(value));bar.setAttribute('aria-valuetext',pct(value));
    const fill=el('div',undefined,'fill');fill.style.width=`${value}%`;bar.append(fill);
  }
  return bar;
}
function validateData(data, timeline) {
  if(data.schema_version!=='1.0.0'||timeline.schema_version!=='1.0.0') throw new Error('数据格式版本不兼容。');
  if(!Array.isArray(data.dimensions)||data.dimensions.length!==4||!Array.isArray(data.groups)||!Array.isArray(timeline.snapshots)||!timeline.snapshots.length) throw new Error('进度数据不完整。');
  const number = (v) => v===null || (typeof v==='number' && Number.isFinite(v) && v>=0 && v<=100);
  const validDate = (v) => typeof v==='string' && Number.isFinite(Date.parse(v));
  for(const snapshot of [data,...timeline.snapshots]) {
    if(!validDate(snapshot.evaluated_at)||!number(snapshot.overall)||!Array.isArray(snapshot.dimensions)||!snapshot.dimensions.every(d=>number(d.score)&&number(d.contribution)&&number(d.manual_score))) throw new Error('进度数值或评估时间无效。');
  }
  if(timeline.snapshots.at(-1).snapshot_id!==data.snapshot_id) throw new Error('当前评估与历史快照不一致，请重试。');
  if(data.published_at!==null&&!validDate(data.published_at)) throw new Error('网站发布时间无效。');
  for(const group of data.groups) {
    if(!Array.isArray(group.children)||!number(group.score)||!group.children.every(t=>t.status===null||Object.hasOwn(labels,t.status))) throw new Error('Todo 数据不完整。');
  }
}
async function load() {
  $('loading').hidden=false;$('error').hidden=true;$('dashboard').hidden=true;
  try {
    const get = async (path) => {const response=await fetch(path,{cache:'no-store'});if(!response.ok) throw new Error(`数据读取失败（HTTP ${response.status}）。`);return response.json();};
    const [data,timeline]=await Promise.all([get('./data/current.json'),get('./data/history.json')]);
    validateData(data,timeline);current=data;history=timeline.snapshots;
    render();$('loading').hidden=true;$('dashboard').hidden=false;
  } catch(error) {
    $('loading').hidden=true;$('error').hidden=false;
    $('error-message').textContent=`${error.message} 当前未显示任何默认分数。请检查连接后重试。`;
  }
}
function render() {
  document.title=current.project.title;
  $('phase').textContent=current.project.phase_label;
  $('evaluated').textContent=dateLabel(current.evaluated_at);
  $('published').textContent=dateLabel(current.published_at);
  $('overall-value').textContent=current.overall===null?'评估待完善':pct(current.overall);
  $('overall-value').classList.toggle('known',current.overall!==null);
  $('overall-meter').replaceChildren(meter(current.overall,'Demo整体完成度'));
  $('overall-reasons').replaceChildren(...current.missing_reasons.map(reason=>el('p',reason)));
  if(!current.missing_reasons.length) $('overall-reasons').append(el('p','必要数据已齐备，按当前已确认规则计算。'));
  renderDimensions();renderUpdates();renderTodos();renderHistory();
  const r=current.rules;
  $('rule-summary').textContent=`剧情 ${Math.round(r.dimension_shares.story*100)}%、美术与场景 ${Math.round(r.dimension_shares.art*100)}%、系统 ${Math.round(r.dimension_shares.system*100)}%、手动打磨 ${Math.round(r.dimension_shares.polish*100)}%。UI 占美术维度 ${Math.round(r.art_ui_share*100)}%。状态计分档位：${Object.values(r.status_factors).map(f=>Math.round(f*100)+'%').join(' / ')}。`;
  $('versions').textContent=`范围 ${current.scope_version} · 规则 ${current.rules_version} · ${r.approval==='confirmed'?'评分规则已确认':'评分规则为草案'} · 数据生成 ${dateLabel(current.generated_at)}（美国东部时间）`;
}
function renderDimensions() {
  $('dimensions').replaceChildren(...current.dimensions.map(d=>{
    const card=el('article',undefined,'dimension-card');card.dataset.dimension=d.id;
    const heading=el('div',undefined,'card-header');heading.append(el('h3',d.label),el('span',`整体权重 ${Math.round(d.share*100)}%`,'weight-tag'));
    const score=el('p',d.score===null?'评估待完善':pct(d.score),`dimension-score${d.score===null?' pending':''}`);
    const contribution=el('p',d.contribution===null?'整体贡献待确认':`贡献整体 ${d.contribution.toFixed(1)} 个百分点`,'contribution');
    const progress=meter(d.score,`${d.label}完成度`);
    if(d.score!==null) progress.firstChild.style.background=colors[d.id];
    card.append(heading,score,progress,contribution,el('p',d.review,'card-review'));
    if(d.id==='art'||d.id==='polish') card.append(el('p',`${d.id==='art'?'UI 完成度':'打磨成熟度'} · 开发者手动评分 ${d.manual_score===null?'待填写':pct(d.manual_score)}`,'manual-line'));
    if(d.remaining.length) {const list=el('ul',undefined,'remaining-list');list.append(...d.remaining.map(t=>el('li',t)));card.append(list);}
    return card;
  }));
}
function renderUpdates() {
  const u=current.update;
  $('delta').textContent=history.length===1?'首次基线':!u.comparable?'评估口径已变化':u.delta===null?'变化待确认':`${signed(u.delta)} 个百分点`;
  $('highlights').replaceChildren(...u.highlights.map(h=>el('li',h)));
  $('change-reasons').replaceChildren(...u.change_reasons.map(r=>el('li',r.text)));
  if(!u.change_reasons.length) $('change-reasons').append(el('li','任务与评分更新，评估口径保持一致。'));
  $('baseline').textContent=current.sources.map(s=>`${s.ref} · ${s.commit.slice(0,7)}`).join(' / ');
}
function renderTodos() {
  const dimension=$('dimension-filter').value,status=$('status-filter').value,scope=$('scope-filter').value;
  const matches = (task) => (status==='all'||(status==='feature_branch'?task.implementation_location==='feature_branch':(task.status||'pending_confirmation')===status)) && (scope!=='remaining'||task.status!=='done') && (scope!=='completed'||task.status==='done');
  const visible=current.groups.filter(g=>(dimension==='all'||g.dimension===dimension)&&g.scope===(scope==='future'?'future':'demo')).map(g=>({...g,visibleChildren:g.children.filter(matches)})).filter(g=>g.visibleChildren.length);
  const taskCount=visible.reduce((n,g)=>n+g.visibleChildren.length,0);
  $('filter-count').textContent=`${visible.length} 个大项 · ${taskCount} 个子项 / Demo 共 ${current.task_counts.total} 个子项`;
  $('empty').hidden=visible.length>0;
  $('todo-groups').replaceChildren(...visible.map(g=>{
    const details=el('details',undefined,'todo-group');details.dataset.id=g.id;
    const summary=el('summary');const left=el('div');left.append(el('span',g.title,'group-name'));
    const subtitle=el('div',undefined,'group-subtitle');subtitle.append(el('span',dimensionNames[g.dimension]),el('span',`${g.visibleChildren.length}/${g.children.length} 子项 · 权重 ${g.weight}`));
    if(g.has_feature_branch) subtitle.append(el('span','含功能分支成果','branch-pill'));
    left.append(subtitle);summary.append(left,pill(g.status));details.append(summary);
    const list=el('ul',undefined,'task-list');
    list.append(...g.visibleChildren.map(t=>{
      const li=el('li',undefined,'task-row');li.dataset.id=t.id;
      const top=el('div',undefined,'task-top');top.append(el('span',t.title,'task-title'),pill(t.status));
      const meta=el('div',undefined,'task-meta');meta.append(el('span',`相对权重 ${t.weight}`));
      if(t.implementation_location==='feature_branch') meta.append(el('span','功能分支已有成果 · 未确认主分支集成','branch-pill'));
      const criteria=el('ul',undefined,'task-criteria');criteria.append(...t.completion_criteria.map(c=>el('li',c)));li.append(top,meta,criteria);return li;
    }));
    details.append(list);return details;
  }));
}
function renderHistory() {
  $('history-count').textContent=`${history.length} 次评估 · 保留当时口径`;
  $('series-controls').replaceChildren(el('legend','显示趋势'));
  for(const [id,name] of Object.entries(seriesNames)) {
    const label=el('label',undefined,'series-label');const input=el('input');input.type='checkbox';input.checked=activeSeries.has(id);input.value=id;input.name='trend-series';
    const dot=el('span',undefined,'series-dot');dot.style.background=colors[id];
    label.append(input,dot,document.createTextNode(name));$('series-controls').append(label);
    input.addEventListener('change',()=>{if(input.checked)activeSeries.add(id);else activeSeries.delete(id);renderChart();});
  }
  $('history-log').replaceChildren(...[...history].reverse().map((snapshot,reverseIndex)=>{
    const entry=el('article',undefined,'history-entry');const date=el('time',dateLabel(snapshot.evaluated_at),'history-date');date.dateTime=snapshot.evaluated_at;
    const body=el('div');const baseline=reverseIndex===history.length-1;
    body.append(el('p',`${baseline?'首次基线':snapshot.update.comparable?'进度更新':'口径变化'} · ${snapshot.overall===null?'整体评估待完善':`整体 ${pct(snapshot.overall)}`}`,'history-score'));
    const tags=el('div',undefined,'history-tags');tags.append(el('span',snapshot.scope_version),el('span',snapshot.rules_version),...snapshot.dimensions.map(d=>el('span',`${d.label} ${pct(d.score)}`)));body.append(tags);
    body.append(el('p',snapshot.update.change_reasons.map(r=>r.text).join(' '),'history-summary'));
    const more=el('details');more.append(el('summary','查看本次成果与评估基线'));
    const list=el('ul');list.append(...snapshot.update.highlights.map(h=>el('li',h)));more.append(list,el('p',snapshot.sources.map(s=>`${s.ref} ${s.commit.slice(0,7)}`).join(' / ')));body.append(more);entry.append(date,body);return entry;
  }));
  renderChart();
}
function svgEl(tag, attrs = {}, text) {
  const e=document.createElementNS('http://www.w3.org/2000/svg',tag);
  for(const [key,value] of Object.entries(attrs)) e.setAttribute(key,String(value));
  if(text!==undefined)e.textContent=text;
  return e;
}
function renderChart() {
  const width=Math.max(280,Math.min(900,window.innerWidth-70)),height=235,left=43,right=25,top=16,bottom=40,plotH=height-top-bottom;
  const svg=svgEl('svg',{viewBox:`0 0 ${width} ${height}`,role:'img','aria-label':'开发完成度历史趋势。未知值不连接，范围或规则变化处分段。'});
  for(const value of [0,25,50,75,100]) {
    const y=top+plotH*(1-value/100);
    svg.append(svgEl('line',{x1:left,x2:width-right,y1:y,y2:y,stroke:'#dde2d3','stroke-dasharray':'3 5'}),svgEl('text',{x:left-10,y:y+4,'text-anchor':'end',fill:'#66705e','font-size':11},`${value}%`));
  }
  const xAt=(index)=>history.length===1?(left+width-right)/2:left+(width-left-right)*index/(history.length-1);
  let known=0;
  for(const id of activeSeries) {
    let previous=null;
    history.forEach((snapshot,i)=>{
      const value=id==='overall'?snapshot.overall:snapshot.dimensions.find(d=>d.id===id)?.score??null;
      if(value===null){previous=null;return;}
      known++;const x=xAt(i),y=top+plotH*(1-value/100);
      const same=previous&&snapshot.scope_version===previous.snapshot.scope_version&&snapshot.rules_version===previous.snapshot.rules_version&&snapshot.project.phase===previous.snapshot.project.phase;
      if(same) svg.append(svgEl('line',{x1:previous.x,y1:previous.y,x2:x,y2:y,stroke:colors[id],'stroke-width':2.2}));
      const point=svgEl('circle',{cx:x,cy:y,r:4,fill:colors[id],stroke:'#fffdf6','stroke-width':1.5});point.append(svgEl('title',{},`${dateLabel(snapshot.evaluated_at)} · ${seriesNames[id]} ${pct(value)}`));svg.append(point);
      if(history.length===1) svg.append(svgEl('text',{x:x+10,y:y-9,fill:colors[id],'font-size':12},`${seriesNames[id]} ${pct(value)}`));
      previous={x,y,snapshot};
    });
  }
  history.forEach((s,i)=>{
    if(history.length>8&&i!==0&&i!==history.length-1&&i%Math.ceil(history.length/6)!==0)return;
    svg.append(svgEl('text',{x:xAt(i),y:height-13,'text-anchor':'middle',fill:'#66705e','font-size':11},dateLabel(s.evaluated_at,true)));
  });
  history.forEach((s,i)=>{
    if(i===0)return;
    const p=history[i-1];
    if(s.scope_version!==p.scope_version||s.rules_version!==p.rules_version||s.project.phase!==p.project.phase){const x=(xAt(i)+xAt(i-1))/2;svg.append(svgEl('line',{x1:x,x2:x,y1:top,y2:top+plotH,stroke:'#9b6945','stroke-dasharray':'5 4'}),svgEl('text',{x:x+5,y:top+12,fill:'#9b6945','font-size':10},'口径变化'));}
  });
  $('chart').replaceChildren(svg);
  $('chart-note').textContent=!activeSeries.size?'尚未选择趋势系列。':!known?'所选系列尚无可绘制的已知分数。未知值没有补成零。':history.length===1?'目前只有首次基线，展示真实已知分数，尚未形成趋势。未知维度不绘制。':'未知值不连接；范围或规则变化处断开。图表记录进展，不预测发布日期。';
}
window.addEventListener('resize',()=>{if(current)renderChart();});
$('retry').addEventListener('click',load);
for(const id of ['dimension-filter','status-filter','scope-filter']) $(id).addEventListener('change',renderTodos);
load();
