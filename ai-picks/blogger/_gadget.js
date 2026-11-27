(function(){
  AI365.css();var el=document.getElementById("a3-gadget"),E=AI365.esc;
  AI365.get("latest_picks.json").then(function(d){
    var h='<div class="a3-card a3-hero"><span class="a3-badge">'+E(d.badge)+'</span>';
    if(d.next){h+='<h2 style="margin-top:6px">'+d.next.draw+'회 AI 실험 번호</h2><div class="a3-meta">'+E(d.next.draw_date)+' 추첨 · 로직 '+E(d.next.version)+' · 추첨 전 공개</div>';
      d.next.sets.forEach(function(s){h+='<div class="a3-row"><span class="a3-lab">'+E(s.label)+'</span>'+AI365.balls(s.nums)+'</div>'});}
    if(d.last_result){var L=d.last_result;h+='<div class="a3-meta" style="margin-top:8px">지난 '+L.draw+'회: AI '+L.ai_total_matches+'개 · 무작위 '+L.random_total_matches+'개 · 기대값 4개 일치</div>';}
    var t=d.track_record;h+='<div class="a3-meta">'+(t.draws?'누적 '+t.draws+'회 · 1장당 평균 '+t.ai_mean+'개 (무작위 '+t.random_mean+' / 기대값 0.8)':E(t.note))+'</div>';
    h+='<div class="a3-meta" style="margin-top:8px"><a href="/p/ai-picks.html" style="color:#fff;font-weight:700">전체 성적표·로직 보기 →</a></div>';
    h+='<div class="a3-meta" style="margin-top:6px;font-size:11px">'+E(d.disclaimer_short)+' · 19세 미만 구매 불가</div></div>';
    el.innerHTML=h;
  }).catch(function(){el.textContent="AI 실험 번호를 불러오지 못했습니다."});
})();
