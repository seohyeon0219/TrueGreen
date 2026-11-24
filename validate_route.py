"""route.json 검사: python scripts/validate_route.py [경로]  — 실패 항목이 있으면 exit 1"""
import json
import sys
from pathlib import Path

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "src/data/route.json"
r = json.loads(path.read_text(encoding="utf-8"))
fails, warns = [], []


def check(ok, msg, warn=False):
    if not ok:
        (warns if warn else fails).append(msg)


stops, segs = r["stops"], r["segments"]
seqs = [s["seq"] for s in stops]
check(seqs == list(range(1, len(stops) + 1)), "stops.seq 가 1부터 빠짐없이 이어지지 않음")
check(len(segs) == len(stops) - 1, f"segments 수 {len(segs)} ≠ stops-1 {len(stops) - 1}")
for g in segs:
    check(g["toSeq"] == g["fromSeq"] + 1, f"구간 {g['idx']}: fromSeq/toSeq 불연속")
    check(g["distanceM"] > 0, f"구간 {g['idx']}: distanceM ≤ 0")
    check(g["distanceM"] < 3000, f"구간 {g['idx']}: {g['distanceM']} m — 정류장 간격치고 김", warn=True)
for s in stops:
    ok = s["lat"] is not None and 37.3 <= s["lat"] <= 37.7 and 126.4 <= s["lng"] <= 126.9
    check(ok, f"좌표가 인천 범위 밖: {s['name']} ({s['lat']}, {s['lng']})")
check({s["dir"] for s in stops} == {"up", "down"}, "상행/하행 구분이 한쪽만 있음", warn=True)

total_km = sum(g["distanceM"] for g in segs) / 1000
check(10 <= total_km <= 40, f"노선 길이 합 {total_km:.1f} km — 확인 필요 (지도 19.6 km, 기사 편도 13.3 km)", warn=True)

idx = {g["idx"] for g in segs}
ids = [s["id"] for s in r["scopes"]]
check("all" in ids, "scope 'all' 없음")
for sc in r["scopes"]:
    check(set(sc["segmentIdx"]) <= idx, f"scope {sc['id']}: 없는 구간 번호")
    check(len(sc["segmentIdx"]) > 0, f"scope {sc['id']}: 구간이 비어 있음")

for h in r["hourlySegments"]:
    tag = f"{h['dayType']} {h['hour']}시 구간{h['segmentIdx']}"
    check(0 <= h["hour"] <= 23, f"{tag}: hour 범위")
    check(h["segmentIdx"] in idx, f"{tag}: 없는 구간")
    check(h["trips"] >= 0 and (h["onboard"] is None or h["onboard"] >= 0), f"{tag}: 음수")
    if h["trips"] and h["onboard"] is not None:
        check(h["avgLoad"] is not None and abs(h["avgLoad"] - h["onboard"] / h["trips"]) < 0.1,
              f"{tag}: avgLoad ≠ onboard/trips")
    if h["speedKmh"] is not None:
        check(5 <= h["speedKmh"] <= 60, f"{tag}: 속도 {h['speedKmh']} km/h", warn=True)

keys = [(h["dayType"], h["hour"], h["segmentIdx"]) for h in r["hourlySegments"]]
check(len(keys) == len(set(keys)), "hourlySegments 중복 키")

for t in ("weekday", "holiday"):
    v = r["avgTripM"].get(t)
    if v is not None:
        check(300 <= v <= 20000, f"avgTripM.{t} = {v} m — 범위 확인", warn=True)
check(len(r["meta"]["sampleDates"]["weekday"]) > 0, "sampleDates.weekday 비어 있음")
check(not r["meta"]["isDummy"] or not r["hourlySegments"], "isDummy=true 인데 시간대 데이터가 있음", warn=True)

for w in warns:
    print("경고:", w)
for f in fails:
    print("실패:", f)
print(f"검사 끝: 실패 {len(fails)}, 경고 {len(warns)}")
sys.exit(1 if fails else 0)
