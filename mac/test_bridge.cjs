const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const source=fs.readFileSync(require('node:path').join(__dirname,'../static/app.js'),'utf8');
function setup(native=true){
    const elements=new Map(), calls=[], timers=new Map();let timer=0;
    const ctx={console, Map, Promise, Error, String, setTimeout:fn=>{timers.set(++timer,fn);return timer},clearTimeout:n=>timers.delete(n),navigator:{},document:{getElementById:id=>{if(!elements.has(id))elements.set(id,{textContent:'',value:'',onclick:null,onchange:null});return elements.get(id)},querySelectorAll:()=>[]}};
    ctx.window=ctx;ctx.SQL_CHECKER_DESKTOP=native;
    if(native)ctx.webkit={messageHandlers:{sqlChecker:{postMessage:msg=>calls.push(msg)}}};
    else ctx.fetch=async()=>({ok:true,json:async()=>({issues:[]})});
    vm.createContext(ctx);vm.runInContext(source,ctx);
    return {ctx,calls,timers,elements};
}
(async()=>{
    const s=setup();
    const success=vm.runInContext("sendSQL('check', 'select 1')",s.ctx);
    assert.equal(s.calls[0].action,'check');assert.equal(s.calls[0].sql,'select 1');
    s.ctx.sqlCheckerReply(s.calls[0].id,{issues:[]},200);assert.equal((await success).issues.length,0);assert.equal(s.timers.size,0);
    const failure=vm.runInContext("sendSQL('format', 'invalid')",s.ctx);
    s.ctx.sqlCheckerReply(s.calls[1].id,{error:'拒绝格式化'},400);await assert.rejects(failure,/拒绝格式化/);
    const timeout=vm.runInContext("sendSQL('check', 'select 2')",s.ctx);
    [...s.timers.values()][0]();await assert.rejects(timeout,/检查超时/);
    s.ctx.sqlCheckerEngineReady();assert.equal(s.elements.get('status').textContent,'引擎已就绪');
    const web=setup(false);assert.equal((await vm.runInContext("sendSQL('check','select 1')",web.ctx)).issues.length,0);
    console.log('Native bridge success, error, timeout, engine readiness and web fallback passed.');
})().catch(e=>{console.error(e);process.exitCode=1});
