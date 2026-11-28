var AI365=(function(){
  var BASE=(window.AI365_BASE||"https://raw.githubusercontent.com/codekimmy/lotto-ai365lab/main/ai-picks/public/");
  function esc(s){return String(s).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]})}
  // o.win: 당첨번호 배열이 있으면 맞은 번호는 검정 채움, 나머지는 흐리게 / o.bonus: 보너스 표시 / o.sm: 작은 공
  function ball(n,o){o=o||{};var c="a3-b";if(o.sm)c+=" a3-sm";
    if(o.bonus)c+=" a3-on";else if(o.win){c+=(o.win.indexOf(n)>=0?" a3-on":" a3-off")}
    return '<i class="'+c+'">'+n+'</i>'}
  function balls(a,o){return a.map(function(n){return ball(n,o)}).join("")}
  function get(f){return fetch(BASE+f+"?t="+Math.floor(Date.now()/300000)).then(function(r){if(!r.ok)throw r.status;return r.json()})}
  function date(s){return String(s).replace(/-/g,".")}
  var M='"JetBrains Mono","IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace';
  var CSS='.a3{color:#111;line-height:1.55}.a3 *{box-sizing:border-box}'+
  '.a3-box{background:#fbf8f0;border:1px solid #111;padding:16px 18px;margin:0 0 16px}'+
  '.a3-k{font-family:'+M+';font-size:12px;letter-spacing:.04em;color:#555;display:flex;justify-content:space-between;gap:8px;border-bottom:1px solid #111;padding-bottom:6px;margin-bottom:10px}'+
  '.a3-h{font-size:24px;font-weight:800;margin:2px 0 2px}.a3-h small{font-size:13px;font-weight:400;color:#555;margin-left:8px;font-family:'+M+'}'+
  '.a3-r{display:flex;align-items:center;flex-wrap:wrap;gap:5px;padding:7px 0;border-top:1px dashed #cfc8b8}.a3-r:first-of-type{border-top:0}'+
  '.a3-l{font-family:'+M+';font-weight:700;min-width:24px;white-space:nowrap;margin-right:4px}.a3-n{font-family:'+M+';font-size:13px;margin-left:6px}'+
  '.a3-why{width:100%;font-size:12px;color:#666;padding-left:33px}'+
  '.a3-b{display:inline-flex;width:30px;height:30px;border:1px solid #111;border-radius:50%;align-items:center;justify-content:center;font-style:normal;font-family:'+M+';font-size:13px;background:#fff;color:#111}'+
  '.a3-sm{width:24px;height:24px;font-size:11px}.a3-on{background:#111;color:#fff}.a3-off{color:#b5ae9f;border-color:#cfc8b8;background:transparent}'+
  '.a3-chip{font-family:'+M+';font-size:11px;background:#d4f53c;border:1px solid #111;padding:0 6px;margin-left:4px}'+
  '.a3-vs{display:grid;grid-template-columns:repeat(3,1fr);border:1px solid #111;margin-top:10px}.a3-vs div{padding:8px;text-align:center;font-size:12px;border-left:1px solid #111}.a3-vs div:first-child{border-left:0}'+
  '.a3-vs b{display:block;font-size:22px;font-family:'+M+'}.a3-vs .a3-me{background:#111;color:#fff}'+
  '.a3 table{width:100%;border-collapse:collapse;font-size:13px}.a3 th{font-family:'+M+';font-size:11px;font-weight:400;color:#555;text-align:left;border-bottom:1px solid #111;padding:4px}'+
  '.a3 td{padding:6px 4px;border-bottom:1px dashed #cfc8b8;vertical-align:top;font-family:'+M+'}'+
  '.a3-note{font-size:12px;color:#555}.a3-warn{font-size:12px;border:1px dashed #111;padding:8px 10px;margin-top:10px}'+
  '.a3-more{display:block;font-family:'+M+';font-size:13px;font-weight:700;color:#111;text-decoration:none;border-top:1px solid #111;padding-top:10px;margin-top:12px}'+
  '.a3-bar{height:8px;background:#e6e0d2;position:relative}.a3-bar span{position:absolute;top:0;bottom:0;left:0;background:#111}.a3-bar em{position:absolute;top:-3px;bottom:-3px;left:50%;border-left:1px dashed #c00}';
  function css(){if(!document.getElementById("a3css2")){var s=document.createElement("style");s.id="a3css2";s.textContent=CSS;document.head.appendChild(s)}}
  // 지난 회차 채점 블록 (가젯·페이지 공용)
  function scoreBlock(r,full){var E=esc,h='';
    h+='<div class="a3-r"><span class="a3-l">당첨</span>'+balls(r.win)+'<span class="a3-n">+</span>'+ball(r.bonus,{bonus:1})+'</div>';
    r.sets.forEach(function(s){h+='<div class="a3-r"><span class="a3-l">'+E(s.label)+'</span>'+balls(s.nums,{win:r.win})+'<span class="a3-n">'+s.matches+'개</span>'+(s.rank?'<span class="a3-chip">'+s.rank+'등</span>':'')+'</div>'});
    if(full&&r.rival){h+='<div class="a3-note" style="margin-top:6px">무작위 대조군 5세트</div>';r.rival.forEach(function(s){h+='<div class="a3-r"><span class="a3-l">·</span>'+balls(s.nums,{win:r.win,sm:1})+'<span class="a3-n">'+s.matches+'개</span></div>'})}
    h+='<div class="a3-vs"><div class="a3-me">AI 5세트<b>'+r.ai_total+'</b></div><div>무작위 5세트<b>'+r.rival_total+'</b></div><div>수학적 기대값<b>4</b></div></div>';
    return h}
  return {esc:esc,ball:ball,balls:balls,get:get,css:css,date:date,scoreBlock:scoreBlock};
})();
