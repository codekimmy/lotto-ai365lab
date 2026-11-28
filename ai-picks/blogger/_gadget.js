(function(){
  AI365.css();var el=document.getElementById("a3-gadget"),E=AI365.esc,B=AI365.balls;
  AI365.get("latest_picks.json").then(function(d){
    var h='';
    if(d.next){var n=d.next;h+='<div class="a3-box"><div class="a3-k"><span>AI 실험 번호 · 재미용 참고</span><span>로직 '+E(n.version)+'</span></div>'+
      '<div class="a3-h">제'+n.draw+'회<small>'+AI365.date(n.draw_date)+' 추첨 예정 · 추첨 전 공개</small></div>';
      n.sets.forEach(function(s){h+='<div class="a3-r"><span class="a3-l">'+E(s.label)+'</span>'+B(s.nums)+'</div>'});h+='</div>';}
    if(d.last_result){var L=d.last_result;
      h+='<div class="a3-box"><div class="a3-k"><span>지난 회차 채점 · 제'+L.draw+'회</span><span>검정 = 맞은 번호</span></div>'+
        AI365.scoreBlock({win:L.win,bonus:L.bonus,sets:L.sets,ai_total:L.ai_total_matches,rival_total:L.random_total_matches});
      if(d.recent&&d.recent.length){h+='<div class="a3-k" style="margin-top:14px"><span>누적 기록</span><span>'+d.track_record.draws+'회 · 1장당 평균 '+d.track_record.ai_mean+' (무작위 '+d.track_record.random_mean+' / 기대 0.8)</span></div>'+
        '<table><tr><th>회차</th><th>AI</th><th>무작위</th><th>기대</th><th>최고 세트</th></tr>';
        d.recent.slice(0,5).forEach(function(x){h+='<tr><td>'+x.draw+'</td><td><b>'+x.ai_total+'</b></td><td>'+x.rival_total+'</td><td>4</td><td>'+x.best_matches+'개'+(x.best_rank?' · '+x.best_rank+'등':'')+'</td></tr>'});h+='</table>';}
      h+='<a class="a3-more" href="/p/ai-picks.html">회차별 전체 기록 · 로직 점검 데이터 →</a></div>';}
    h+='<div class="a3-note" style="margin:-8px 0 16px">'+E(d.disclaimer_short)+' · 19세 미만 구매 불가</div>';
    el.innerHTML=h;
  }).catch(function(){el.textContent="AI 실험 번호를 불러오지 못했습니다."});
})();
