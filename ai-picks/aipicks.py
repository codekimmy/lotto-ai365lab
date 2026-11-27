"""
Ai365Lab AI 실험 번호 엔진 (표준 라이브러리만 사용)

사용법 (저장소 루트에서):
  python ai-picks/aipicks.py update      # 결과 수집 → 채점 → 다음 회차 번호 생성 → 성적표/JSON/HTML 갱신
  python ai-picks/aipicks.py backtest    # 사후 백테스트(실전 성적 아님) 다시 계산
  python ai-picks/aipicks.py pick 1252   # 특정 회차 번호만 계산해서 출력(저장 안 함)

원칙
- 로또는 매 회차 독립 추첨이고 모든 조합의 1등 확률은 1/8,145,060으로 같다. 이 엔진은 확률을 올리지 못한다.
- 번호는 추첨 전에 저장소에 커밋해 공개한다(커밋 시각 = 사전 공개 증거). 공개 후에는 절대 고치지 않는다.
- 같은 회차·같은 버전이면 누가 돌려도 같은 번호가 나온다(시드 고정).
"""
import hashlib
import html
import json
import math
import os
import random
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
PUB = os.path.join(ROOT, "public")
HIST = os.path.join(DATA, "history.json")
MANUAL = os.path.join(DATA, "manual_results.json")
PICKS_DIR = os.path.join(DATA, "picks")
KST = timezone(timedelta(hours=9))

DISCLAIMER = ("로또는 매 회차 독립 추첨이라 어떤 방법으로도 당첨 확률을 높일 수 없습니다. "
              "Ai365Lab 번호는 AI 실험·재미용 참고 번호이며 당첨을 예측하거나 보장하지 않습니다. "
              "복권 구매는 여유 자금 안에서 하시고, 19세 미만은 구매할 수 없습니다.")

# ───────────────────────── 로직 버전 ─────────────────────────
# 버전을 바꿀 때는 아래 dict를 새로 추가하고 ACTIVE만 바꾼다. 옛 버전은 지우지 않는다.
VERSIONS = {
    "v1.0": {
        "effective_from": 1252,
        "name": "4지표 앙상블 + 구조 필터",
        "weights": {"recent50": 0.35, "all": 0.15, "gap": 0.30, "neighbor": 0.20},
        "temperature": 0.6,      # 점수 → 뽑힐 가중치 변환 강도
        "samples": 30000,        # 시드 고정 후보 조합 수
        "filters": {
            "sum_pct": (10, 90),       # 역대 합계 분포 10~90백분위
            "odd": (2, 4),
            "low": (2, 4),             # 1~22 개수
            "max_consec_pairs": 1,
            "max_per_band": 3,         # 1-9,10-19,20-29,30-39,40-45
            "max_prev_overlap": 2,     # 직전 회차와 겹침
        },
        "max_set_overlap": 2,          # 5세트끼리 겹치는 번호 상한
        "max_number_uses": 2,          # 한 번호가 5세트에 쓰이는 횟수 상한
    }
}
ACTIVE = "v1.0"

# 등수별 정확 확률(1장 기준). 분모 C(45,6)=8,145,060
C45_6 = math.comb(45, 6)
RANK_P = {
    1: 1 / C45_6,
    2: 6 / C45_6,
    3: (math.comb(6, 5) * 38) / C45_6,           # 5개 일치, 보너스 불일치
    4: (math.comb(6, 4) * math.comb(39, 2)) / C45_6,
    5: (math.comb(6, 3) * math.comb(39, 3)) / C45_6,
}
EXP_MATCH_PER_TICKET = 6 * 6 / 45  # 0.8


# ───────────────────────── 데이터 ─────────────────────────
def load_json(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_json(p, obj, compact=False):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        if compact:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        else:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Ai365Lab results bot)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8")


def fetch_draw(n):
    """회차 결과를 가져온다. 1순위: 수동 입력 파일, 2순위: 동행복권 공식(국내 IP에서만 될 수 있음),
    3순위: smok95/lotto 공개 미러(GitHub). 공식과 미러가 둘 다 응답하면 서로 맞는지 확인한다."""
    manual = load_json(MANUAL, {}) or {}
    if str(n) in manual:
        m = manual[str(n)]
        return {"draw": n, "date": m["date"], "nums": sorted(m["nums"]), "bonus": m["bonus"], "source": "manual"}

    official = None
    try:
        d = json.loads(_get(f"https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={n}", 15))
        if d.get("returnValue") == "success":
            official = {"draw": n, "date": d["drwNoDate"],
                        "nums": sorted(d[f"drwtNo{i}"] for i in range(1, 7)), "bonus": d["bnusNo"],
                        "source": "dhlottery"}
    except Exception as e:  # 해외 IP 차단·주소 변경 등
        print(f"[info] 공식 사이트 조회 실패({n}회): {type(e).__name__}")

    mirror = None
    for br in ("main", "master"):
        try:
            d = json.loads(_get(f"https://raw.githubusercontent.com/smok95/lotto/{br}/results/{n}.json"))
            if d.get("draw_no") == n:
                mirror = {"draw": n, "date": d["date"][:10], "nums": sorted(d["numbers"]),
                          "bonus": d["bonus_no"], "source": "smok95-mirror"}
                break
        except Exception:
            continue

    if official and mirror and (official["nums"] != mirror["nums"] or official["bonus"] != mirror["bonus"]):
        print(f"[warn] {n}회 공식과 미러 불일치 → 공식 값 사용")
    return official or mirror


def update_history():
    hist = load_json(HIST, [])
    added = []
    while True:
        n = len(hist) + 1
        r = fetch_draw(n)
        if not r:
            break
        _validate(r)
        hist.append({k: r[k] for k in ("draw", "date", "nums", "bonus")})
        added.append((n, r["source"]))
    if added:
        save_json(HIST, hist, compact=True)
    return hist, added


def _validate(r):
    ns = r["nums"]
    assert len(ns) == 6 and len(set(ns)) == 6 and all(1 <= x <= 45 for x in ns), r
    assert 1 <= r["bonus"] <= 45 and r["bonus"] not in ns, r


# ───────────────────────── 로직 ─────────────────────────
def _z(vals):
    m = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals)) or 1.0
    return [(v - m) / sd for v in vals]


def number_scores(hist, cfg):
    """hist = 예측 회차 직전까지의 결과만. 미래 데이터는 절대 쓰지 않는다."""
    N = range(1, 46)
    allc = {n: 0 for n in N}
    rec = {n: 0 for n in N}
    last_seen = {n: 0 for n in N}
    for i, r in enumerate(hist):
        for x in r["nums"]:
            allc[x] += 1
            last_seen[x] = i + 1
            if i >= len(hist) - 50:
                rec[x] += 1
    T = len(hist)
    gap = {n: T - last_seen[n] for n in N}
    prev = set(hist[-1]["nums"])
    neigh = {n: (1.0 if (n - 1 in prev or n + 1 in prev) else 0.0) + (0.5 if n in prev else 0.0) for n in N}

    feats = {
        "recent50": _z([rec[n] for n in N]),
        "all": _z([allc[n] for n in N]),
        # 공백: 기대 간격 7.5회 대비 얼마나 오래 쉬었나 (상한 4배)
        "gap": _z([min(gap[n] / 7.5, 4.0) for n in N]),
        "neighbor": _z([neigh[n] for n in N]),
    }
    w = cfg["weights"]
    score = {n: sum(w[k] * feats[k][n - 1] for k in w) for n in N}
    detail = {n: {"recent50": rec[n], "all": allc[n], "gap": gap[n],
                  "neighbor": neigh[n] > 0, "score": round(score[n], 3)} for n in N}
    return score, detail


def _sum_band(hist, lo_pct, hi_pct):
    s = sorted(sum(r["nums"]) for r in hist)
    return s[int(len(s) * lo_pct / 100)], s[min(len(s) - 1, int(len(s) * hi_pct / 100))]


def _passes(c, f, band, prev):
    if not (band[0] <= sum(c) <= band[1]):
        return False
    odd = sum(x % 2 for x in c)
    if not (f["odd"][0] <= odd <= f["odd"][1]):
        return False
    low = sum(x <= 22 for x in c)
    if not (f["low"][0] <= low <= f["low"][1]):
        return False
    if sum(1 for a, b in zip(c, c[1:]) if b - a == 1) > f["max_consec_pairs"]:
        return False
    bands = [min(x // 10, 4) for x in c]
    if max(bands.count(b) for b in set(bands)) > f["max_per_band"]:
        return False
    if len(prev & set(c)) > f["max_prev_overlap"]:
        return False
    return True


def seed_for(version, draw):
    return int(hashlib.sha256(f"Ai365Lab-{version}-{draw}".encode()).hexdigest()[:16], 16)


def make_picks(hist, draw, version=ACTIVE):
    cfg = VERSIONS[version]
    assert hist[-1]["draw"] == draw - 1, "직전 회차까지의 데이터가 필요합니다"
    score, detail = number_scores(hist, cfg)
    weight = {n: math.exp(cfg["temperature"] * s) for n, s in score.items()}
    rng = random.Random(seed_for(version, draw))
    band = _sum_band(hist, *cfg["filters"]["sum_pct"])
    prev = set(hist[-1]["nums"])
    pool = list(range(1, 46))

    seen, cands = set(), []
    for _ in range(cfg["samples"]):
        # 가중치 비복원 추출 (Efraimidis–Spirakis)
        keys = sorted(pool, key=lambda n: rng.random() ** (1.0 / weight[n]), reverse=True)
        c = tuple(sorted(keys[:6]))
        if c in seen:
            continue
        seen.add(c)
        if _passes(c, cfg["filters"], band, prev):
            cands.append((sum(score[n] for n in c) / 6, c))
    cands.sort(key=lambda t: (-t[0], t))

    chosen, uses = [], {n: 0 for n in pool}
    for sc, c in cands:
        if any(len(set(c) & set(p)) > cfg["max_set_overlap"] for _, p in chosen):
            continue
        if any(uses[n] >= cfg["max_number_uses"] for n in c):
            continue
        chosen.append((sc, c))
        for n in c:
            uses[n] += 1
        if len(chosen) == 5:
            break

    top = sorted(score, key=lambda n: -score[n])[:10]
    sets = []
    for i, (sc, c) in enumerate(chosen):
        sets.append({
            "label": "ABCDE"[i],
            "nums": list(c),
            "sum": sum(c),
            "odd_even": f"{sum(x % 2 for x in c)}:{6 - sum(x % 2 for x in c)}",
            "low_high": f"{sum(x <= 22 for x in c)}:{6 - sum(x <= 22 for x in c)}",
            "reason": _reason(c, detail),
        })
    return {
        "draw": draw,
        "version": version,
        "logic": cfg["name"],
        "seed": f"sha256('Ai365Lab-{version}-{draw}')",
        "data_through": hist[-1]["draw"],
        "sets": sets,
        "top10_numbers": [{"n": n, **detail[n]} for n in top],
        "sum_band": list(band),
    }


def _reason(c, d):
    hot = [n for n in c if d[n]["recent50"] >= 9]
    cold = [n for n in c if d[n]["gap"] >= 15]
    nb = [n for n in c if d[n]["neighbor"]]
    out = []
    if hot:
        out.append("최근 50회 자주 나옴 " + "·".join(map(str, hot)))
    if cold:
        out.append("15회 이상 쉼 " + "·".join(map(str, cold)))
    if nb:
        out.append("직전 회차 번호·이웃 " + "·".join(map(str, nb)))
    return " / ".join(out) or "균형형"


def random_rival(draw):
    """같은 조건의 대조군: 시드 고정 완전 무작위 5세트."""
    rng = random.Random(seed_for("random-rival", draw))
    return [sorted(rng.sample(range(1, 46), 6)) for _ in range(5)]


# ───────────────────────── 채점 ─────────────────────────
def rank_of(nums, res):
    m = len(set(nums) & set(res["nums"]))
    b = res["bonus"] in nums
    if m == 6:
        return m, 1
    if m == 5 and b:
        return m, 2
    return m, {5: 3, 4: 4, 3: 5}.get(m, 0)


def score_draw(pick, res):
    rows = []
    for s in pick["sets"]:
        m, rk = rank_of(s["nums"], res)
        rows.append({"label": s["label"], "matches": m, "rank": rk,
                     "hit": sorted(set(s["nums"]) & set(res["nums"]))})
    rival = []
    for nums in pick.get("random_rival") or random_rival(pick["draw"]):
        m, rk = rank_of(nums, res)
        rival.append({"matches": m, "rank": rk})
    return {"result": {"nums": res["nums"], "bonus": res["bonus"], "date": res["date"]},
            "sets": rows, "rival": rival,
            "ai_total": sum(r["matches"] for r in rows),
            "rival_total": sum(r["matches"] for r in rival),
            "best_rank": min([r["rank"] for r in rows if r["rank"]] or [0])}


def summarize(entries):
    """entries: 채점된 회차 리스트. 기대값은 정확 확률로 계산(무작위 5장 기준)."""
    D = len(entries)
    T = 5 * D
    ai_m = sum(e["score"]["ai_total"] for e in entries)
    rv_m = sum(e["score"]["rival_total"] for e in entries)
    ranks = {k: 0 for k in range(1, 6)}
    rv_ranks = {k: 0 for k in range(1, 6)}
    for e in entries:
        for s in e["score"]["sets"]:
            if s["rank"]:
                ranks[s["rank"]] += 1
        for s in e["score"]["rival"]:
            if s["rank"]:
                rv_ranks[s["rank"]] += 1
    p3plus = sum(RANK_P.values())
    hits3 = sum(ranks.values())
    exp3 = T * p3plus
    # 1장당 일치 개수 분산(초기하분포): 6*(6/45)*(39/45)*(39/44)
    var1 = 6 * (6 / 45) * (39 / 45) * (39 / 44)
    se_mean = math.sqrt(var1 / T) if T else 0
    mean_ai = ai_m / T if T else 0
    return {
        "draws": D, "tickets": T,
        "ai_mean_matches": round(mean_ai, 3),
        "rival_mean_matches": round(rv_m / T, 3) if T else 0,
        "expected_mean_matches": round(EXP_MATCH_PER_TICKET, 3),
        "z_vs_expected": round((mean_ai - EXP_MATCH_PER_TICKET) / se_mean, 2) if T else 0,
        "ai_rank_counts": ranks,
        "rival_rank_counts": rv_ranks,
        "expected_rank_counts": {k: round(T * p, 3) for k, p in RANK_P.items()},
        "ai_hits_3plus": hits3,
        "expected_hits_3plus": round(exp3, 2),
        "ai_best_rank_ever": min([k for k, v in ranks.items() if v] or [0]),
    }


# ───────────────────────── 재검토 규칙 ─────────────────────────
REVIEW_RULE = {
    "window": 20,          # 최근 20회(100장)를 본다
    "min_draws_between_changes": 10,
    "triggers": [
        "최근 20회 1장당 평균 일치 개수가 무작위 기대값 0.8개보다 낮고, 같은 기간 무작위 대조군보다도 낮을 때",
        "최근 20회 3개 이상 적중(5등 이상) 장수가 무작위 기대값(약 2.38장)의 절반 미만일 때",
    ],
    "note": "어떤 로직도 장기적으로 무작위를 이길 근거는 없습니다. 재검토는 '더 잘 맞히기'보다 실험을 투명하게 이어가기 위한 절차입니다.",
}


def review_status(entries, version):
    mine = [e for e in entries if e["version"] == version and not e.get("backtest")]
    w = REVIEW_RULE["window"]
    if len(mine) < w:
        return {"state": "관찰 중", "detail": f"{version} 실전 {len(mine)}회 / 판단에는 {w}회 필요"}
    s = summarize(mine[-w:])
    t1 = s["ai_mean_matches"] < s["expected_mean_matches"] and s["ai_mean_matches"] < s["rival_mean_matches"]
    t2 = s["ai_hits_3plus"] < s["expected_hits_3plus"] / 2
    if t1 or t2:
        return {"state": "재검토 필요", "detail": "; ".join(x for x, f in zip(REVIEW_RULE["triggers"], (t1, t2)) if f),
                "window_stats": s}
    return {"state": "유지", "detail": f"최근 {w}회 기준 재검토 조건 해당 없음", "window_stats": s}


# ───────────────────────── 실행 ─────────────────────────
def next_draw_date(hist):
    last = datetime.strptime(hist[-1]["date"], "%Y-%m-%d")
    return (last + timedelta(days=7)).strftime("%Y-%m-%d")


def cmd_update():
    hist, added = update_history()
    print(f"history: {len(hist)}회까지, 새로 추가 {added}")
    os.makedirs(PICKS_DIR, exist_ok=True)
    byn = {r["draw"]: r for r in hist}

    # 1) 채점: 결과가 나온 공개 번호
    for fn in sorted(os.listdir(PICKS_DIR)):
        p = load_json(os.path.join(PICKS_DIR, fn))
        if p.get("score") is None and p["draw"] in byn:
            p["score"] = score_draw(p, byn[p["draw"]])
            save_json(os.path.join(PICKS_DIR, fn), p)
            print(f"채점 {p['draw']}회: AI {p['score']['ai_total']}개 / 무작위 {p['score']['rival_total']}개")

    # 2) 다음 회차 번호 생성 (이미 있으면 절대 덮어쓰지 않음)
    nxt = hist[-1]["draw"] + 1
    path = os.path.join(PICKS_DIR, f"{nxt}.json")
    if not os.path.exists(path):
        ver = max((v for v, c in VERSIONS.items() if c["effective_from"] <= nxt), key=lambda v: VERSIONS[v]["effective_from"])
        pk = make_picks(hist, nxt, ver)
        pk["draw_date"] = next_draw_date(hist)
        pk["generated_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
        pk["random_rival"] = random_rival(nxt)
        pk["score"] = None
        save_json(path, pk)
        print(f"{nxt}회 번호 생성:", [s["nums"] for s in pk["sets"]])

    build_outputs(hist)


def cmd_backtest(n=100):
    hist = load_json(HIST)
    out = []
    end = hist[-1]["draw"]
    for d in range(end - n + 1, end + 1):
        pk = make_picks(hist[:d - 1], d, ACTIVE)
        pk["random_rival"] = random_rival(d)
        pk["score"] = score_draw(pk, hist[d - 1])
        pk["backtest"] = True
        out.append({"draw": d, "version": ACTIVE, "backtest": True, "score": pk["score"],
                    "sets": [s["nums"] for s in pk["sets"]]})
    res = {"version": ACTIVE, "range": [end - n + 1, end],
           "note": "로직 v1.0을 과거 회차에 거꾸로 적용한 결과입니다. 실전 성적이 아니며, 과거에 맞춘 로직은 미래에 같은 성과를 내지 않습니다.",
           "summary": summarize(out), "draws": out}
    save_json(os.path.join(DATA, "backtest_v1.0.json"), res)
    print(json.dumps(res["summary"], ensure_ascii=False, indent=1))
    return res


def build_outputs(hist):
    os.makedirs(PICKS_DIR, exist_ok=True)
    picks = [load_json(os.path.join(PICKS_DIR, f)) for f in sorted(os.listdir(PICKS_DIR))]
    scored = [p for p in picks if p.get("score")]
    upcoming = [p for p in picks if not p.get("score")]
    live = summarize(scored) if scored else None
    bt = load_json(os.path.join(DATA, "backtest_v1.0.json"))
    review = review_status(scored, ACTIVE)
    nxt = upcoming[-1] if upcoming else None
    last = scored[-1] if scored else None

    scorecard = {
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
        "active_version": ACTIVE,
        "live": live,
        "backtest_summary": bt["summary"] if bt else None,
        "review": review,
        "review_rule": REVIEW_RULE,
        "rank_probability_per_ticket": {k: f"1/{round(1 / p):,}" for k, p in RANK_P.items()},
        "history": [{"draw": p["draw"], "version": p["version"], "sets": [s["nums"] for s in p["sets"]],
                     **({"result": p["score"]["result"], "ai_total": p["score"]["ai_total"],
                         "rival_total": p["score"]["rival_total"], "best_rank": p["score"]["best_rank"],
                         "set_scores": p["score"]["sets"]} if p.get("score") else {})} for p in picks],
        "disclaimer": DISCLAIMER,
    }
    save_json(os.path.join(PUB, "scorecard.json"), scorecard)

    # 릴스·카드 생성기용 작은 JSON
    reel = {
        "schema": "ai365lab.picks/1",
        "updated_at": scorecard["updated_at"],
        "title": f"이번 주 Ai365Lab AI 실험 번호" if nxt else "",
        "badge": "AI 실험 · 재미용 참고 번호",
        "next": ({"draw": nxt["draw"], "draw_date": nxt["draw_date"], "version": nxt["version"],
                  "logic": nxt["logic"],
                  "sets": [{"label": s["label"], "nums": s["nums"], "reason": s["reason"]} for s in nxt["sets"]],
                  "generated_at": nxt["generated_at"]} if nxt else None),
        "last_result": ({"draw": last["draw"], "win": last["score"]["result"]["nums"],
                         "bonus": last["score"]["result"]["bonus"],
                         "best_set": max(last["score"]["sets"], key=lambda s: s["matches"]),
                         "ai_total_matches": last["score"]["ai_total"],
                         "random_total_matches": last["score"]["rival_total"],
                         "expected_total_matches": 4.0} if last else None),
        "track_record": ({"draws": live["draws"], "ai_mean": live["ai_mean_matches"],
                          "random_mean": live["rival_mean_matches"], "expected_mean": 0.8,
                          "hits_3plus": live["ai_hits_3plus"],
                          "expected_hits_3plus": live["expected_hits_3plus"]} if live else
                         {"draws": 0, "note": "1252회부터 실전 기록 시작"}),
        "review_state": review["state"],
        "disclaimer_short": "당첨 확률을 높이지 않습니다 · 재미용 참고 번호",
        "disclaimer": DISCLAIMER,
    }
    save_json(os.path.join(PUB, "latest_picks.json"), reel)
    with open(os.path.join(PUB, "index.html"), "w", encoding="utf-8") as f:
        f.write(render_html(scorecard, nxt, bt))
    print("outputs: public/scorecard.json, public/latest_picks.json, public/index.html")


def _balls(nums, hit=()):
    return "".join(f'<b class="ball{" hit" if n in hit else ""} c{min((n - 1) // 10, 4)}">{n}</b>' for n in nums)


def render_html(sc, nxt, bt):
    e = html.escape
    live = sc["live"]
    parts = []
    if nxt:
        rows = "".join(f'<div class="set"><span class="lab">{s["label"]}</span>{_balls(s["nums"])}'
                       f'<small>{e(s["reason"])}</small></div>' for s in nxt["sets"])
        parts.append(f'<section><h2>{nxt["draw"]}회 AI 실험 번호 <em>{e(nxt["draw_date"])} 추첨</em></h2>'
                     f'<p class="meta">로직 {e(nxt["version"])} · {e(nxt["logic"])} · 공개 {e(nxt["generated_at"])}'
                     f' · {nxt["data_through"]}회까지 데이터 사용</p>{rows}</section>')
    if live:
        parts.append(
            f'<section><h2>실전 성적표 (공개 후 채점, {live["draws"]}회 · {live["tickets"]}장)</h2>'
            f'<table><tr><th></th><th>AI 번호</th><th>무작위 대조군</th><th>수학적 기대값</th></tr>'
            f'<tr><td>1장당 평균 일치</td><td>{live["ai_mean_matches"]}</td><td>{live["rival_mean_matches"]}</td><td>0.8</td></tr>'
            f'<tr><td>3개 이상 적중(5등↑)</td><td>{live["ai_hits_3plus"]}장</td><td>{sum(live["rival_rank_counts"].values())}장</td><td>{live["expected_hits_3plus"]}장</td></tr>'
            + "".join(f'<tr><td>{k}등</td><td>{live["ai_rank_counts"][k]}</td><td>{live["rival_rank_counts"][k]}</td><td>{live["expected_rank_counts"][k]}</td></tr>' for k in range(1, 6))
            + "</table></section>")
    else:
        parts.append('<section><h2>실전 성적표</h2><p>1252회부터 기록을 시작합니다. 추첨 다음 날 자동 채점됩니다.</p></section>')
    hist_rows = ""
    for h in reversed(sc["history"]):
        if "result" in h:
            win = h["result"]["nums"]
            cells = "".join(f'<div>{_balls(s, win)} <small>{len(set(s) & set(win))}개</small></div>' for s in h["sets"])
            hist_rows += (f'<tr><td>{h["draw"]}회<br><small>{e(h["version"])}</small></td><td>{_balls(win)} +{h["result"]["bonus"]}</td>'
                          f'<td>{cells}</td><td>AI {h["ai_total"]} / 무작위 {h["rival_total"]}</td></tr>')
    if hist_rows:
        parts.append(f'<section><h2>회차별 기록</h2><table class="hist"><tr><th>회차</th><th>당첨번호</th><th>AI 5세트</th><th>일치 합계</th></tr>{hist_rows}</table></section>')
    if bt:
        s = bt["summary"]
        parts.append(f'<section><h2>참고: 사후 백테스트 {bt["range"][0]}~{bt["range"][1]}회</h2>'
                     f'<p class="warn">{e(bt["note"])}</p>'
                     f'<p>1장당 평균 일치 {s["ai_mean_matches"]}개 (기대값 0.8, 무작위 대조군 {s["rival_mean_matches"]}) · '
                     f'3개 이상 적중 {s["ai_hits_3plus"]}장 (기대값 {s["expected_hits_3plus"]}장)</p></section>')
    rv = sc["review"]
    parts.append(f'<section><h2>로직 상태: {e(rv["state"])}</h2><p>{e(rv["detail"])}</p><ul>'
                 + "".join(f"<li>{e(t)}</li>" for t in sc["review_rule"]["triggers"])
                 + f'</ul><p class="meta">{e(sc["review_rule"]["note"])}</p></section>')
    probs = " · ".join(f"{k}등 {v}" for k, v in sc["rank_probability_per_ticket"].items())
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ai365Lab AI 실험 번호 · 성적표</title>
<style>
body{{margin:0;font-family:Pretendard,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;background:#f6f3ff;color:#241a3d}}
header{{background:linear-gradient(135deg,#3b1e7a,#7b4fd6);color:#fff;padding:28px 20px}}
header h1{{margin:0 0 6px;font-size:24px}} header p{{margin:0;opacity:.9;font-size:14px}}
main{{max-width:860px;margin:0 auto;padding:16px}}
section{{background:#fff;border-radius:16px;padding:18px;margin:14px 0;box-shadow:0 2px 10px #3b1e7a14}}
h2{{font-size:18px;margin:0 0 10px}} h2 em{{font-style:normal;font-size:13px;color:#7b4fd6;margin-left:6px}}
.meta{{color:#6b5f86;font-size:13px}} .warn{{background:#fff4e5;padding:8px 10px;border-radius:8px;font-size:13px}}
.set{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:8px 0;border-top:1px solid #eee}}
.set small{{color:#6b5f86;width:100%;padding-left:34px}}
.lab{{width:26px;font-weight:800;color:#7b4fd6}}
.ball{{display:inline-flex;width:32px;height:32px;border-radius:50%;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:14px;margin:1px}}
.c0{{background:#f2b705}}.c1{{background:#3b82f6}}.c2{{background:#ef4444}}.c3{{background:#6b7280}}.c4{{background:#22a06b}}
.hist .ball{{opacity:.35;width:24px;height:24px;font-size:11px}} .hist .ball.hit{{opacity:1;outline:2px solid #241a3d}}
table{{width:100%;border-collapse:collapse;font-size:14px}} td,th{{padding:6px;border-bottom:1px solid #eee;text-align:left;vertical-align:top}}
footer{{font-size:12px;color:#6b5f86;padding:10px 16px 40px;max-width:860px;margin:0 auto}}
</style></head><body>
<header><h1>Ai365Lab AI 실험 번호</h1><p>추첨 전에 공개하고, 추첨 후 무작위 번호와 나란히 채점합니다. 안 맞으면 기록에 그대로 남습니다.</p></header>
<main>{''.join(parts)}</main>
<footer><p><b>{e(sc["disclaimer"])}</b></p><p>1장 기준 등수별 확률: {probs} (어떤 번호든 동일)</p>
<p>업데이트 {e(sc["updated_at"])} · 당첨번호 출처: 동행복권 공식 결과(공개 미러 smok95/lotto 경유, 공식 사이트에서 최종 확인 권장)</p></footer>
</body></html>"""


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else "update"
    if c == "update":
        cmd_update()
    elif c == "backtest":
        cmd_backtest(int(sys.argv[2]) if len(sys.argv) > 2 else 100)
        build_outputs(load_json(HIST))
    elif c == "pick":
        h = load_json(HIST)
        d = int(sys.argv[2])
        print(json.dumps(make_picks(h[:d - 1], d), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
