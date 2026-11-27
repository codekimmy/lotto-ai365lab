(function(){
  AI365.css();var el=document.getElementById("a3-page"),E=AI365.esc,B=AI365.balls;
  Promise.all([AI365.get("latest_picks.json"),AI365.get("scorecard.json")]).then(function(r){
    var d=r[0],sc=r[1],h='';
    // 1. 이번 주 번호
    if(d.next){var n=d.next;h+='<div class="a3-card a3-hero"><span class="a3-badge">'+E(d.badge)+'</span><h2 style="margin-top:6px">'+n.draw+'회 AI 실험 번호</h2>'+
      '<div class="a3-meta">'+E(n.draw_date)+' 추첨 · 로직 '+E(n.version)+' ('+E(n.logic)+') · 공개 '+E(n.generated_at)+'</div>';
      n.sets.forEach(function(s){h+='<div class="a3-row"><span class="a3-lab">'+E(s.label)+'</span>'+B(s.nums)+'<span class="a3-why">'+E(s.reason)+'</span></div>'});
      h+='<div class="a3-meta" style="margin-top:6px">공개 시각 증거: <a style="color:#fff" href="https://github.com/codekimmy/lotto-ai365lab/commits/main/ai-picks/data/picks" target="_blank" rel="noopener">GitHub 커밋 기록</a> · 공개 후에는 고치지 않습니다.</div></div>';}
    // 2. 지난 회차 채점
    var hist=sc.history.filter(function(x){return x.result});
    if(hist.length){var L=hist[hist.length-1],w=L.result.nums;
      h+='<div class="a3-card"><h2>'+L.draw+'회 채점</h2><div class="a3-row" style="border:0">당첨 '+B(w)+' <span class="a3-meta">+보너스 '+L.result.bonus+'</span></div>';
      L.sets.forEach(function(s,i){var ss=L.set_scores[i];h+='<div class="a3-row"><span class="a3-lab">'+"ABCDE"[i]+'</span>'+B(s,{win:w})+' <b style="margin-left:4px">'+ss.matches+'개</b>'+(ss.rank?' <span class="a3-badge">'+ss.rank+'등</span>':'')+'</div>'});
      h+='<div class="a3-vs" style="margin-top:8px"><div>AI 5세트<b>'+L.ai_total+'개</b></div><div>무작위 5세트<b>'+L.rival_total+'개</b></div><div>수학적 기대값<b>4개</b></div></div></div>';}
    // 3. 누적 성적표
    var lv=sc.live;
    h+='<div class="a3-card"><h2>누적 성적표 · AI 대 무작위</h2>';
    if(lv){h+='<div class="a3-meta">실전 '+lv.draws+'회 · '+lv.tickets+'장 (추첨 전 공개한 번호만 채점)</div><table><tr><th></th><th>AI</th><th>무작위</th><th>기대값</th></tr>'+
      '<tr><td>1장당 평균 일치</td><td>'+lv.ai_mean_matches+'</td><td>'+lv.rival_mean_matches+'</td><td>0.8</td></tr>';
      var rs=function(o){var t=0;for(var k in o)t+=o[k];return t};
      h+='<tr><td>3개 이상(5등↑)</td><td>'+lv.ai_hits_3plus+'장</td><td>'+rs(lv.rival_rank_counts)+'장</td><td>'+lv.expected_hits_3plus+'장</td></tr>';
      for(var k=1;k<=5;k++)h+='<tr><td>'+k+'등</td><td>'+lv.ai_rank_counts[k]+'</td><td>'+lv.rival_rank_counts[k]+'</td><td>'+lv.expected_rank_counts[k]+'</td></tr>';
      h+='</table>';}else h+='<p>1252회부터 기록을 시작합니다. 추첨 다음 날 자동으로 채점돼요.</p>';
    if(sc.backtest_summary){var b=sc.backtest_summary;h+='<p class="a3-warn">참고(실전 아님): v1.0을 지난 '+b.draws+'회에 거꾸로 적용하면 1장당 평균 '+b.ai_mean_matches+'개 일치(무작위 대조군 '+b.rival_mean_matches+', 기대값 0.8), 3개 이상 '+b.ai_hits_3plus+'장(기대값 '+b.expected_hits_3plus+'장). 무작위와 구별되지 않는 수준입니다.</p>';}
    h+='</div>';
    // 4. 회차별 기록
    if(hist.length){h+='<div class="a3-card"><h2>회차별 기록</h2><table><tr><th>회차</th><th>AI 5세트 (맞은 번호 진하게)</th><th>AI / 무작위</th></tr>';
      hist.slice().reverse().forEach(function(x){h+='<tr><td>'+x.draw+'회<br><span class="a3-meta">'+E(x.version)+'</span></td><td>'+x.sets.map(function(s){return '<div>'+B(s,{win:x.result.nums,small:1})+'</div>'}).join('')+'</td><td>'+x.ai_total+' / '+x.rival_total+'</td></tr>'});
      h+='</table></div>';}
    // 5. 로직 상태·규칙·이력
    var rv=sc.review;h+='<div class="a3-card"><h2>로직 상태: '+E(rv.state)+'</h2><div class="a3-meta">'+E(rv.detail)+'</div><h3 style="margin-top:10px">재검토 규칙 (최근 '+sc.review_rule.window+'회 기준)</h3><ul style="margin:0;padding-left:18px;font-size:13px">';
    sc.review_rule.triggers.forEach(function(t){h+='<li>'+E(t)+'</li>'});
    h+='</ul><p class="a3-meta">로직은 최소 '+sc.review_rule.min_draws_between_changes+'회 간격으로만 바꾸고, 옛 버전 기록은 지우지 않습니다. '+E(sc.review_rule.note)+'</p>';
    h+='<h3 style="margin-top:10px">로직 변경 이력</h3><table><tr><th>버전</th><th>적용</th><th>내용</th></tr>';
    sc.changelog.slice().reverse().forEach(function(c){h+='<tr><td>'+E(c.version)+'</td><td>'+c.effective_from+'회~<br><span class="a3-meta">'+E(c.published||'')+'</span></td><td>'+E(c.note)+'</td></tr>'});
    h+='</table></div>';
    // 6. 면책
    var p=sc.rank_probability_per_ticket;
    h+='<div class="a3-card a3-disc"><b>'+E(sc.disclaimer)+'</b><br>1장 기준 확률(어떤 번호든 같음): 1등 '+p[1]+' · 2등 '+p[2]+' · 3등 '+p[3]+' · 4등 '+p[4]+' · 5등 '+p[5]+'<br>업데이트 '+E(sc.updated_at)+' · 당첨번호 원본은 동행복권 공식 사이트에서 확인하세요.</div>';
    el.innerHTML=h;
  }).catch(function(){el.textContent="성적표를 불러오지 못했습니다. 잠시 후 새로고침해 주세요."});
})();
