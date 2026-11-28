(function(){
  AI365.css();var el=document.getElementById("a3-page"),E=AI365.esc,B=AI365.balls;
  Promise.all([AI365.get("latest_picks.json"),AI365.get("scorecard.json")]).then(function(r){
    var d=r[0],sc=r[1],h='';
    if(d.next){var n=d.next;h+='<div class="a3-box"><div class="a3-k"><span>이번 주 AI 실험 번호</span><span>로직 '+E(n.version)+' · 공개 '+E(n.generated_at)+'</span></div>'+
      '<div class="a3-h">제'+n.draw+'회<small>'+AI365.date(n.draw_date)+' 추첨 예정</small></div>';
      n.sets.forEach(function(s){h+='<div class="a3-r"><span class="a3-l">'+E(s.label)+'</span>'+B(s.nums)+'<span class="a3-why">'+E(s.reason)+'</span></div>'});
      h+='<div class="a3-note" style="margin-top:8px">공개 시각 증거: <a href="https://github.com/codekimmy/lotto-ai365lab/commits/main/ai-picks/data/picks" target="_blank" rel="noopener">GitHub 커밋 기록</a> · 공개 후에는 고치지 않습니다.</div></div>';}
    var lv=sc.live;
    h+='<div class="a3-box"><div class="a3-k"><span>누적 성적표 · AI 대 무작위</span><span>'+(lv?'실전 '+lv.draws+'회 · '+lv.tickets+'장':'기록 시작 전')+'</span></div>';
    if(lv){var rs=function(o){var t=0;for(var k in o)t+=o[k];return t};
      h+='<table><tr><th></th><th>AI</th><th>무작위</th><th>기대값</th></tr><tr><td>1장당 평균 일치</td><td><b>'+lv.ai_mean_matches+'</b></td><td>'+lv.rival_mean_matches+'</td><td>0.8</td></tr>'+
        '<tr><td>3개 이상(5등↑)</td><td><b>'+lv.ai_hits_3plus+'</b></td><td>'+rs(lv.rival_rank_counts)+'</td><td>'+lv.expected_hits_3plus+'</td></tr>';
      for(var k=1;k<=5;k++)h+='<tr><td>'+k+'등</td><td>'+lv.ai_rank_counts[k]+'</td><td>'+lv.rival_rank_counts[k]+'</td><td>'+lv.expected_rank_counts[k]+'</td></tr>';h+='</table>';}
    if(sc.backtest_summary){var b=sc.backtest_summary;h+='<div class="a3-warn">참고(실전 아님): v1.0을 1152~1251회에 거꾸로 적용하면 1장당 평균 '+b.ai_mean_matches+'개(무작위 '+b.rival_mean_matches+', 기대 0.8), 3개 이상 '+b.ai_hits_3plus+'장(기대 '+b.expected_hits_3plus+'장). 무작위와 구별되지 않는 수준입니다.</div>';}
    h+='</div>';
    // 회차별 누적 기록
    h+='<div class="a3-box"><div class="a3-k"><span>회차별 기록 · 추천 번호 대 실제 당첨번호</span><span>검정 = 맞은 번호</span></div>';
    if(sc.history.length){sc.history.forEach(function(x,i){
      h+='<div style="'+(i?'border-top:1px solid #111;margin-top:14px;padding-top:12px':'')+'"><div class="a3-h" style="font-size:19px">제'+x.draw+'회<small>로직 '+E(x.version)+'</small></div>'+AI365.scoreBlock(x,true)+'</div>'});}
    else h+='<p class="a3-note">1252회부터 쌓입니다.</p>';
    h+='</div>';
    // 로직 점검 데이터
    var dg=sc.diagnostics;
    if(dg){h+='<div class="a3-box"><div class="a3-k"><span>로직 점검 데이터</span><span>당첨번호의 지표 순위 · 무작위면 50%</span></div><p class="a3-note" style="margin-top:0">'+E(dg.how_to_read)+'</p>'+
      '<table><tr><th>지표</th><th>실전 평균</th><th></th><th>백테스트 100회</th></tr>';
      dg.features.forEach(function(f){var lvv=dg.live_avg?dg.live_avg[f.key]:null,bt=dg.backtest_avg?dg.backtest_avg[f.key]:null;
        h+='<tr><td style="font-family:inherit">'+E(f.label)+'</td><td>'+(lvv==null?'-':'상위 '+lvv+'%')+'</td><td style="width:30%"><div class="a3-bar"><span style="width:'+(lvv==null?0:100-lvv)+'%"></span><em></em></div></td><td>'+(bt==null?'-':'상위 '+bt+'%')+'</td></tr>'});
      h+='</table><p class="a3-note">막대가 빨간 점선(50%)보다 길면 그 지표가 당첨번호 쪽을 가리켰다는 뜻입니다. 한두 회차는 우연이 크니 20회 이상 쌓인 값으로 판단합니다.</p></div>';}
    // 상태·규칙·이력
    var rv=sc.review;h+='<div class="a3-box"><div class="a3-k"><span>로직 상태</span><span>'+E(rv.state)+'</span></div><p class="a3-note" style="margin-top:0">'+E(rv.detail)+'</p><b>재검토 규칙 (최근 '+sc.review_rule.window+'회 기준)</b><ul style="margin:4px 0;padding-left:18px;font-size:13px">';
    sc.review_rule.triggers.forEach(function(t){h+='<li>'+E(t)+'</li>'});
    h+='</ul><p class="a3-note">로직은 최소 '+sc.review_rule.min_draws_between_changes+'회 간격으로만 바꾸고, 옛 버전 기록은 지우지 않습니다. '+E(sc.review_rule.note)+'</p>'+
      '<div class="a3-k" style="margin-top:12px"><span>로직 변경 이력</span><span></span></div><table><tr><th>버전</th><th>적용</th><th>내용</th></tr>';
    sc.changelog.slice().reverse().forEach(function(c){h+='<tr><td>'+E(c.version)+'</td><td>'+c.effective_from+'회~</td><td style="font-family:inherit">'+E(c.note)+'</td></tr>'});
    h+='</table></div>';
    var p=sc.rank_probability_per_ticket;
    h+='<div class="a3-note"><b>'+E(sc.disclaimer)+'</b><br>1장 기준 확률(어떤 번호든 같음): 1등 '+p[1]+' · 2등 '+p[2]+' · 3등 '+p[3]+' · 4등 '+p[4]+' · 5등 '+p[5]+'<br>업데이트 '+E(sc.updated_at)+' · 당첨번호 원본은 동행복권 공식 사이트에서 확인하세요.</div>';
    el.innerHTML=h;
  }).catch(function(){el.textContent="성적표를 불러오지 못했습니다. 잠시 후 새로고침해 주세요."});
})();
