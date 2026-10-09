const $=id=>document.getElementById(id);let issues=[],checkedSQL='';
const sample="select\n    a.region\n    ,b.shipper_id\n    ,sum(a.amount) / sum(a.cnt) as `平均金额`\nfrom orders a\nleft join shippers b on a.shipper_id = a.shipper_id\nwhere a.dt between '${month_1}' and '${dt}'\ngroup by\n    a.region\n";
$('example').onclick=()=>{$('sql').value=sample;$('status').textContent='已载入示例'};
function show(){const root=$('results');root.replaceChildren();const list=issues.filter(x=>$('filter').value==='all'||x.severity===$('filter').value);if(!list.length){const p=document.createElement('p');p.textContent=issues.length?'当前筛选下没有问题':'未发现静态问题；仍需在 DLI 验证。';root.append(p)}for(const item of list){const row=document.createElement('div');row.className='issue';const badge=document.createElement('span');badge.className='badge '+item.severity;badge.textContent={error:'错误',warning:'风险',info:'建议'}[item.severity];const meta=document.createElement('span');meta.className='meta';meta.textContent=`第 ${item.line} 行 · 第 ${item.column} 列 · ${item.category} · ${item.code}`;const reason=document.createElement('p');reason.textContent=item.reason;const hint=document.createElement('p');hint.className='suggestion';hint.textContent='建议：'+item.suggestion;row.append(badge,meta,reason,hint);row.onclick=()=>{if($('sql').value!==checkedSQL){$('status').textContent='SQL 已变化，请重新检查后定位';return}const lines=$('sql').value.split('\n');let start=lines.slice(0,item.line-1).reduce((n,l)=>n+l.length+1,0);$('sql').focus();$('sql').setSelectionRange(start,start+(lines[item.line-1]||'').length);$('sql').scrollTop=Math.max(0,(item.line-3)*23)};root.append(row)}}
$('filter').onchange=show;
let busy = false;
const desktopReplies = new Map();
let requestNumber = 0;
window.sqlCheckerReply = (id, data, status) => {
    const pending = desktopReplies.get(id);
    if (!pending) return;
    clearTimeout(pending.timer);
    desktopReplies.delete(id);
    if (status >= 200 && status < 300) pending.resolve(data);
    else pending.reject(Error(data.error || '检查失败'));
};
window.sqlCheckerEngineReady = () => {
    window.SQL_CHECKER_ENGINE_READY = true;
    if (!busy && $('status').textContent === '正在准备检查引擎，可先输入 SQL…') $('status').textContent = '引擎已就绪';
};
window.sqlCheckerEngineFailed = () => {
    if (!busy) $('status').textContent = '检查引擎启动失败，可复制 SQL 后重新打开应用';
};
if (window.SQL_CHECKER_DESKTOP) $('status').textContent = '正在准备检查引擎，可先输入 SQL…';
async function sendSQL(action, sql) {
    if (window.webkit?.messageHandlers?.sqlChecker) {
        const id = String(++requestNumber);
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => { desktopReplies.delete(id); reject(Error('检查超时，请缩短 SQL 后重试')); }, 60000);
            desktopReplies.set(id, {resolve, reject, timer});
            window.webkit.messageHandlers.sqlChecker.postMessage({id, action, sql});
        });
    }
    const response = await fetch('/api/' + action, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({sql})});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || '请求失败');
    return data;
}
async function run(action){busy=true;$('status').textContent='处理中…';document.querySelectorAll('button').forEach(b=>b.disabled=true);try{const data=await sendSQL(action,$('sql').value);if(action==='check'){issues=data.issues;checkedSQL=$('sql').value;$('summary').textContent=`检查结果 · ${issues.filter(x=>x.severity==='error').length} 错误 / ${issues.filter(x=>x.severity==='warning').length} 风险 / ${issues.filter(x=>x.severity==='info').length} 建议`;show()}else{$('sql').value=data.sql;issues=[];checkedSQL='';$('results').replaceChildren();$('summary').textContent='已格式化，请重新检查'}$('status').textContent='完成'}catch(e){$('status').textContent=e.message}finally{busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false)}}
$('check').onclick=()=>run('check');$('format').onclick=()=>run('format');async function copy(text){try{await navigator.clipboard.writeText(text);$('status').textContent='已复制'}catch{const t=document.createElement('textarea');t.value=text;document.body.append(t);t.select();document.execCommand('copy');t.remove();$('status').textContent='已复制'}}$('copy').onclick=()=>copy($('sql').value);$('copyreport').onclick=()=>copy(issues.map(x=>`第${x.line}行:${x.column} [${x.severity}] ${x.category} ${x.code}\n${x.reason}\n建议：${x.suggestion}`).join('\n\n'));
