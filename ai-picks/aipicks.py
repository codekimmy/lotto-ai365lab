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
        "published": "2026-11-27",
        "note": "최초 공개. 최근50회 빈도·쉰 기간·직전 회차 이웃·전체 빈도 가중합 + 홀짝·저고·합계·연속·번호대 필터, 5세트. 무작위 대조군 동시 공개.",
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
    },
    "v1.1": {
        "effective_from": 1253,
        "name": "4지표 앙상블 + 구조 필터 + 주간 회전",
        "published": "2026-11-28",
        "note": ("v1.0은 점수 상위 조합만 골라 매주 같은 번호가 반복됐음(1252→1253회 18개 중 11개 재등장). "
                 "성적 때문이 아니라 '같은 번호를 민다'로 보이는 구조 문제라 수정. "
                 "① 점수 순 선택 대신 점수 가중 추첨 순서로 선택 ② 직전 회차 AI 번호에 감점 "
                 "③ 새 세트는 직전 회차 AI 세트 어느 것과도 2개 이하, 직전 AI 번호 전체와 3개 이하만 겹침 "
                 "④ 세트끼리 겹침 1개 이하 ⑤ 매주 바뀌는 지표(쉰 기간·직전 이웃) 비중을 높이고 느린 지표 비중을 낮춤."),
        "weights": {"recent50": 0.20, "all": 0.05, "gap": 0.40, "neighbor": 0.35},
        "temperature": 0.6,
        "samples": 30000,
        "filters": {
            "sum_pct": (10, 90),
            "odd": (2, 4),
            "low": (2, 4),
            "max_consec_pairs": 1,
            "max_per_band": 3,
            "max_prev_overlap": 2,
        },
        "max_set_overlap": 1,
        "max_number_uses": 2,
        "select": "sampled",           # 점수 순(top)이 아니라 가중 추첨 순서대로
        "carry_penalty": 0.8,          # 직전 회차 AI 번호 감점(표준점수 단위)
        "max_prev_set_overlap": 2,     # 직전 AI 세트 하나와 겹침 상한
        "max_prev_pool_overlap": 3,    # 직전 AI 번호 전체와 겹침 상한
    },
}
ACTIVE = "v1.1"

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


def make_picks(hist, draw, version=ACTIVE, prev_sets=None):
    """prev_sets: 직전 회차에 공개한 AI 5세트(v1.1부터 반복 방지에 사용)."""
    cfg = VERSIONS[version]
    assert hist[-1]["draw"] == draw - 1, "직전 회차까지의 데이터가 필요합니다"
    score, detail = number_scores(hist, cfg)
    prev_sets = [set(x) for x in (prev_sets or [])]
    prev_pool = set().union(*prev_sets) if prev_sets else set()
    if cfg.get("carry_penalty") and prev_pool:
        score = {n: v - (cfg["carry_penalty"] if n in prev_pool else 0) for n, v in score.items()}
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
        if not _passes(c, cfg["filters"], band, prev):
            continue
        if prev_sets and "max_prev_set_overlap" in cfg:
            if any(len(set(c) & p) > cfg["max_prev_set_overlap"] for p in prev_sets):
                continue
            if len(set(c) & prev_pool) > cfg["max_prev_pool_overlap"]:
                continue
        cands.append((sum(score[n] for n in c) / 6, c))
    if cfg.get("select", "top") == "top":
        cands.sort(key=lambda t: (-t[0], t))
    # "sampled": 점수 가중 추첨으로 나온 순서 그대로 사용(점수 높은 번호가 더 자주 나오지만 매주 고정되지 않음)

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


FEATURES = [("recent50", "최근 50회 빈도"), ("gap", "쉰 기간"), ("neighbor", "직전 회차 이웃"),
            ("all", "전체 빈도"), ("score", "종합 점수")]


def diagnose(hist_before, win, version):
    """로직 개선용 근거 데이터: 실제 당첨번호 6개가 각 지표에서 45개 중 몇 위였나(상위 %).
    무작위라면 평균 약 50%. 50%보다 꾸준히 낮으면(=상위) 그 지표가 쓸모 있었다는 뜻, 높으면 반대."""
    _, d = number_scores(hist_before, VERSIONS[version])
    out = {}
    for k, _lab in FEATURES:
        val = {n: float(d[n][k]) for n in d}
        pct = []
        for w in win:
            higher = sum(1 for n in val if val[n] > val[w])
            ties = sum(1 for n in val if val[n] == val[w]) - 1
            pct.append((higher + ties / 2) / 44 * 100)
        out[k] = round(sum(pct) / len(pct), 1)
    return out


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
            p["score"]["diagnostics"] = diagnose(hist[:p["draw"] - 1], byn[p["draw"]]["nums"], p["version"])
            save_json(os.path.join(PICKS_DIR, fn), p)
            print(f"채점 {p['draw']}회: AI {p['score']['ai_total']}개 / 무작위 {p['score']['rival_total']}개")
        elif p.get("score") and "diagnostics" not in p["score"]:
            p["score"]["diagnostics"] = diagnose(hist[:p["draw"] - 1], p["score"]["result"]["nums"], p["version"])
            save_json(os.path.join(PICKS_DIR, fn), p)

    # 2) 다음 회차 번호 생성 (이미 있으면 절대 덮어쓰지 않음)
    nxt = hist[-1]["draw"] + 1
    path = os.path.join(PICKS_DIR, f"{nxt}.json")
    if not os.path.exists(path):
        ver = max((v for v, c in VERSIONS.items() if c["effective_from"] <= nxt), key=lambda v: VERSIONS[v]["effective_from"])
        prev_pk = load_json(os.path.join(PICKS_DIR, f"{nxt - 1}.json"))
        pk = make_picks(hist, nxt, ver, [x["nums"] for x in prev_pk["sets"]] if prev_pk else None)
        pk["draw_date"] = next_draw_date(hist)
        pk["generated_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
        pk["random_rival"] = random_rival(nxt)
        pk["score"] = None
        save_json(path, pk)
        print(f"{nxt}회 번호 생성:", [s["nums"] for s in pk["sets"]])

    build_outputs(hist)


def cmd_backtest(n=100, end=None, version=ACTIVE):
    """사후 백테스트 범위는 버전과 관계없이 1152~1251회로 고정(버전끼리 같은 구간에서 비교)."""
    hist = load_json(HIST)
    out = []
    end = end or 1251
    prev_sets = None
    for d in range(end - n + 1, end + 1):
        pk = make_picks(hist[:d - 1], d, version, prev_sets)
        prev_sets = [s["nums"] for s in pk["sets"]]
        pk["random_rival"] = random_rival(d)
        pk["score"] = score_draw(pk, hist[d - 1])
        pk["score"]["diagnostics"] = diagnose(hist[:d - 1], hist[d - 1]["nums"], version)
        pk["backtest"] = True
        out.append({"draw": d, "version": version, "backtest": True, "score": pk["score"],
                    "sets": [s["nums"] for s in pk["sets"]]})
    res = {"version": version, "range": [end - n + 1, end],
           "note": f"로직 {version}을 과거 회차에 거꾸로 적용한 결과입니다. 실전 성적이 아니며, 과거에 맞춘 로직은 미래에 같은 성과를 내지 않습니다.",
           "summary": summarize(out), "repeat": repeat_stats([e["sets"] for e in out]),
           "diagnostics_avg": _diag_avg(out), "draws": out}
    save_json(os.path.join(DATA, f"backtest_{version}.json"), res)
    print(json.dumps(res["summary"], ensure_ascii=False, indent=1))
    return res


def repeat_stats(weeks):
    """주간 반복 지표. weeks = 회차 순서대로 [[6개]*5, ...]"""
    pool_ov, max_pair, carry_sets = [], [], []
    for a, b in zip(weeks, weeks[1:]):
        A = [set(x) for x in a]
        B = [set(x) for x in b]
        ua, ub = set().union(*A), set().union(*B)
        pool_ov.append(len(ua & ub) / len(ub))
        max_pair.append(max(len(x & y) for x in B for y in A))
        carry_sets.append(sum(1 for x in B if len(x & ua) >= 4))
    k = len(pool_ov) or 1
    return {"weeks": len(pool_ov),
            "reused_share": round(sum(pool_ov) / k * 100, 1),
            "avg_max_pair_overlap": round(sum(max_pair) / k, 2),
            "worst_pair_overlap": max(max_pair) if max_pair else 0,
            "avg_sets_with_4plus_reused": round(sum(carry_sets) / k, 2)}


def _diag_avg(entries):
    ds = [e["score"]["diagnostics"] for e in entries if e["score"].get("diagnostics")]
    if not ds:
        return None
    return {k: round(sum(d[k] for d in ds) / len(ds), 1) for k, _ in FEATURES}


def _hist_row(p):
    sc = p["score"]
    win = sc["result"]["nums"]
    return {"draw": p["draw"], "version": p["version"], "win": win, "bonus": sc["result"]["bonus"],
            "sets": [{"label": s["label"], "nums": s["nums"], "matches": r["matches"], "rank": r["rank"],
                      "hit": r["hit"]} for s, r in zip(p["sets"], sc["sets"])],
            "rival": [{"nums": n, "matches": r["matches"]} for n, r in
                      zip(p.get("random_rival") or random_rival(p["draw"]), sc["rival"])],
            "ai_total": sc["ai_total"], "rival_total": sc["rival_total"], "expected_total": 4.0,
            "best_rank": sc["best_rank"], "diagnostics": sc.get("diagnostics")}


def build_outputs(hist):
    os.makedirs(PICKS_DIR, exist_ok=True)
    picks = [load_json(os.path.join(PICKS_DIR, f)) for f in sorted(os.listdir(PICKS_DIR))]
    scored = [p for p in picks if p.get("score")]
    upcoming = [p for p in picks if not p.get("score")]
    live = summarize(scored) if scored else None
    bt = load_json(os.path.join(DATA, f"backtest_{ACTIVE}.json")) or load_json(os.path.join(DATA, "backtest_v1.0.json"))
    review = review_status(scored, ACTIVE)
    nxt = upcoming[-1] if upcoming else None
    last = scored[-1] if scored else None

    scorecard = {
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
        "active_version": ACTIVE,
        "live": live,
        "backtest_summary": bt["summary"] if bt else None,
        "backtest_version": bt["version"] if bt else None,
        "backtest_repeat": bt.get("repeat") if bt else None,
        "review": review,
        "review_rule": REVIEW_RULE,
        "changelog": [{"version": v, "effective_from": c["effective_from"], "published": c.get("published"),
                       "name": c["name"], "note": c.get("note", ""), "weights": c["weights"]}
                      for v, c in sorted(VERSIONS.items(), key=lambda kv: kv[1]["effective_from"])],
        # 추첨 전에 폐기한 번호(투명성 기록). 채점 대상 아님
        "withdrawn": [{"draw": w["draw"], "version": w["version"], "sets": [x["nums"] for x in w["sets"]],
                       "generated_at": w.get("generated_at"), **w["withdrawn"]}
                      for w in (load_json(os.path.join(DATA, "withdrawn", f)) for f in
                                sorted(os.listdir(os.path.join(DATA, "withdrawn")))
                                if f.endswith(".json"))] if os.path.isdir(os.path.join(DATA, "withdrawn")) else [],
        "rank_probability_per_ticket": {k: f"1/{round(1 / p):,}" for k, p in RANK_P.items()},
        # 회차별 누적 기록(최신순). 로직 재검토의 근거 데이터
        "history": [_hist_row(p) for p in reversed(scored)],
        "diagnostics": {
            "features": [{"key": k, "label": lab} for k, lab in FEATURES],
            "how_to_read": "실제 당첨번호 6개가 각 지표 순위에서 평균 상위 몇 %였는지. 무작위면 약 50%. 낮을수록 그 지표가 당첨번호 쪽을 가리켰다는 뜻",
            "live_avg": _diag_avg(scored),
            "backtest_avg": bt.get("diagnostics_avg") if bt else None,
        },
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
                         "sets": _hist_row(last)["sets"],
                         "ai_total_matches": last["score"]["ai_total"],
                         "random_total_matches": last["score"]["rival_total"],
                         "expected_total_matches": 4.0} if last else None),
        # 최근 회차 누적 요약(최신순, 최대 10회)
        "recent": [{"draw": p["draw"], "ai_total": p["score"]["ai_total"], "rival_total": p["score"]["rival_total"],
                    "best_matches": max(r["matches"] for r in p["score"]["sets"]),
                    "best_rank": p["score"]["best_rank"]} for p in list(reversed(scored))[:10]],
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
    print("outputs: public/scorecard.json, public/latest_picks.json")


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else "update"
    if c == "update":
        cmd_update()
    elif c == "backtest":
        cmd_backtest(int(sys.argv[2]) if len(sys.argv) > 2 else 100,
                     int(sys.argv[3]) if len(sys.argv) > 3 else None,
                     sys.argv[4] if len(sys.argv) > 4 else ACTIVE)
        build_outputs(load_json(HIST))
    elif c == "pick":
        h = load_json(HIST)
        d = int(sys.argv[2])
        print(json.dumps(make_picks(h[:d - 1], d), ensure_ascii=False, indent=1))
    else:
        print(__doc__)
