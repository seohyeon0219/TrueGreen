"""
701번 route.json 생성 (types.ts의 RouteData 형식)  — 데이터 담당: 현승

입력 (data/raw/ 아래에 둔다. 파일명은 CONFIG에서 바꿀 수 있음)
  route_stops.csv       인천광역시_버스노선별 정류장 현황 (2026-06-30)   정류장 순서·ID·번호·구간거리
  stop_coords.csv       인천광역시_시내버스 정류소 현황 (2026-02-28)     정류소ID·위경도
  stop_onoff.csv        (선택) 정류장별 하루 승하차, 모든 노선 합계      지도 참고용
  ic_section/701_YYYYMMDD.json   인천 대중교통 통계 API Bus_Route_Section_OPHour 응답 (날짜별)
  boardings_daily/YYYYMMDD.json  (선택) 국토부 정류장별 경유노선별 이용량 응답 (701번 하루 승차)
  boardings_hourly.csv  (선택) date,hour,stopNo,boardings  — 시간대별 701번 승차 출처를 찾으면

실행
  python scripts/build_route.py            -> src/data/route.json
  python scripts/validate_route.py         -> 검사

원본 열 이름이 CONFIG 후보와 다르면, 실제 열 목록을 출력하고 멈춘다. 후보에 추가하면 된다.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "src" / "data" / "route.json"

CONFIG = {
    "routeNo": "701",
    "operator": "인천교통공사",
    "turnStopName": "가정(루원시티)역",       # 회차 정류장: 여기까지 up, 다음부터 down
    # 노선현황(2026-09-30): 첫차 04:35, 막차 24:32, 운행 92회, 배차 최소 8·최대 20분, 휴일 배차 열 없음
    # weekday = 운행시간대 1,197분 ÷ 92회 ≈ 13.0분 (평균). API 시간대 데이터가 오면 시간대별 60÷trips로 대체
    "headwayMin": {"weekday": 13.0, "holiday": None},
    "officialTripsPerDay": 92,                 # 노선현황 운행횟수 (1회 = 기점→회차→기점 왕복)
    "vehicleFuel": None,                       # 태동님 확인 후
    "coreStops": ["청라호수공원한신더휴아파트", "청라우미린아파트", "청라중앙호수공원입구",
                  "롯데마트", "초은고등학교"],
    "sources": {
        "stops": "인천광역시_버스노선별 정류장 현황 (2026-06-30), data.go.kr 15048265",
        "coords": "인천광역시_시내버스 정류소 현황 (2026-02-28), data.go.kr 15074309",
        "headway": "인천시 시내버스 노선현황 (2026-09-30) — 배차 최소 8·최대 20분, 92회/일, 평균 13.0분으로 환산",
        "hourly": "인천광역시_대중교통 통계 조회 서비스 API (ICPubTrans_v2) 2026-06 평균 — 9월 데이터 미제공(2026-07-31까지 제공)",
    },
    "holidays": {"2026-09-24", "2026-09-25", "2026-09-26"},  # 추석 연휴
    "month": (2026, 9),
}

# 원본 열 이름 후보 (앞에서부터 찾음)
COLS = {
    "routeNo": ["노선번호", "노선명", "ROUTE_NO", "routeNo"],
    "seq": ["정류소순번", "정류장순번", "순번", "경유순서", "PATHSEQ"],
    "stopId": ["정류소아이디", "정류소ID", "정류소 ID", "정류장ID", "BSTOPID"],
    "stopNo": ["정류소번호", "정류장번호", "정류소 번호", "단축번호", "SHORT_BSTOPID"],
    "name": ["정류소명", "정류장명", "BSTOPNM"],
    "dir": ["상_하행", "방향"],
    "dist": ["정류소구간거리", "구간거리", "구간거리(m)", "정류장간거리", "DIST"],
    "lat": ["위도", "Y좌표", "POSY", "lat"],
    "lng": ["경도", "X좌표", "POSX", "lng"],
    "onoff": ["일평균 승하차인원수", "승하차", "승하차건수", "합계", "onoff"],
    # API 응답 필드 (키 받은 뒤 probe로 확인해서 채움)
    "api_seq": ["STOP_SEQ", "PATHSEQ", "seq"],
    "api_hour": ["HOUR", "TIME", "hour"],
    "api_onboard": ["ONBOARD", "RIDE_CNT", "onboard"],
    "api_trips": ["OP_CNT", "RUN_CNT", "trips"],
    "api_runtime": ["RUN_TIME", "SEC_TIME", "runTime"],
    "api_route": ["ROUTE_NO", "rte_no", "routeName"],
    "api_stop_name": ["sttn_nm", "BSTOPNM"],
    "api_board": ["ride_nope", "ride_cnt", "BOARD_CNT"],
}

notes: list[str] = []


# ---------------------------------------------------------------- 유틸
def read_csv(path: Path) -> list[dict]:
    for enc in ("utf-8-sig", "cp949"):
        try:
            with path.open(encoding=enc, newline="") as f:
                return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]
        except UnicodeDecodeError:
            continue
    sys.exit(f"{path.name}: 인코딩을 읽지 못했습니다 (utf-8/cp949 아님)")


def col(rows: list[dict], key: str, file: str, required=True) -> str | None:
    header = rows[0].keys() if rows else []
    for c in COLS[key]:
        if c in header:
            return c
    if required:
        sys.exit(f"{file}: '{key}' 열을 못 찾음. 실제 열: {list(header)} → COLS['{key}']에 추가하세요")
    return None


def pick(row: dict, key: str):
    for c in COLS[key]:
        if c in row and row[c] not in ("", None):
            return row[c]
    return None


def num(x) -> float | None:
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def norm(s: str) -> str:
    return re.sub(r"\s+", "", re.sub(r"\(.*?\)", "", s or ""))


def api_items(obj) -> list[dict]:
    stack = [obj]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            for k in ("item", "items", "data"):
                v = n.get(k)
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    return v
            stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
        elif isinstance(n, list):
            stack.extend(n)
    return []


def sample_dates() -> dict[str, list[str]]:
    y, m = CONFIG["month"]
    d = dt.date(y, m, 1)
    wk, ho = [], []
    while d.month == m:
        s = d.isoformat()
        if s in CONFIG["holidays"] or d.weekday() == 6:
            ho.append(s)
        elif d.weekday() < 5:
            wk.append(s)
        d += dt.timedelta(days=1)
    return {"weekday": wk, "holiday": ho}


# ---------------------------------------------------------------- 단계
def build_stops():
    rows = read_csv(RAW / "route_stops_701.csv")
    c_route = col(rows, "routeNo", "route_stops.csv")
    rows = [r for r in rows if r[c_route].strip() == CONFIG["routeNo"]]
    if not rows:
        sys.exit("route_stops.csv 에 701번 행이 없습니다")
    c_seq, c_id, c_no, c_nm = (col(rows, k, "route_stops.csv") for k in ("seq", "stopId", "stopNo", "name"))
    c_dist = col(rows, "dist", "route_stops.csv")
    rows.sort(key=lambda r: int(num(r[c_seq])))

    # 좌표
    crow = read_csv(RAW / "stop_coords_701.csv")
    c_cid = col(crow, "stopId", "stop_coords.csv")
    c_a, c_b = col(crow, "lat", "stop_coords.csv"), col(crow, "lng", "stop_coords.csv")
    coords = {}
    swapped = 0
    for r in crow:
        a, b = num(r[c_a]), num(r[c_b])
        if a is None or b is None:
            continue
        if 124 <= a <= 132 and 33 <= b <= 39:   # 열 이름이 바뀐 경우
            a, b = b, a
            swapped += 1
        coords[r[c_cid]] = (round(a, 6), round(b, 6))
    if swapped:
        notes.append(f"정류소 현황 위도·경도 열이 바뀐 행 {swapped}개를 값 범위로 바로잡음")

    # 지도 참고용 승하차 (선택)
    onoff = {}
    p = RAW / "stop_onoff_701.csv"
    if p.exists():
        orows = read_csv(p)
        c_ono, c_val = col(orows, "stopNo", "stop_onoff.csv"), col(orows, "onoff", "stop_onoff.csv")
        onoff = {r[c_ono]: num(r[c_val]) for r in orows}

    c_dir = col(rows, "dir", "route_stops.csv", required=False)
    stops, dist_raw = [], []
    direction = "up"
    for r in rows:
        sid = r[c_id]
        if sid not in coords:
            notes.append(f"좌표 없음: {r[c_nm]} ({sid})")
        lat, lng = coords.get(sid, (None, None))
        if c_dir:
            direction = "up" if r[c_dir].strip() == "상행" else "down"
        stops.append({
            "seq": int(num(r[c_seq])), "stopId": sid, "stopNo": r[c_no], "name": r[c_nm],
            "lat": lat, "lng": lng, "dir": direction,
            "dailyOnOffAllRoutes": round(onoff[r[c_no]]) if onoff.get(r[c_no]) is not None else None,
        })
        dist_raw.append(num(r[c_dist]) or 0.0)
        if not c_dir and norm(r[c_nm]) == norm(CONFIG["turnStopName"]):
            direction = "down"
    if not c_dir and direction == "up":
        notes.append(f"회차 정류장 '{CONFIG['turnStopName']}'을 못 찾아 전부 up으로 둠")

    # 구간거리 기준 판별
    if dist_raw[0] == 0:            # 행 n = (n-1 → n)
        seg_d = dist_raw[1:]
        notes.append("구간거리 = 이전 정류장→이 정류장 기준으로 판별")
    elif dist_raw[-1] == 0:         # 행 n = (n → n+1)
        seg_d = dist_raw[:-1]
        notes.append("구간거리 = 이 정류장→다음 정류장 기준으로 판별")
    else:
        seg_d = dist_raw[1:]
        notes.append("구간거리 기준 판별 불가(첫·끝 행 모두 0 아님) → 이전→이 정류장으로 가정, 확인 필요")

    segments = []
    for i, (a, b) in enumerate(zip(stops, stops[1:])):
        segments.append({"idx": i, "fromSeq": a["seq"], "toSeq": b["seq"],
                         "dir": a["dir"], "distanceM": round(seg_d[i])})
    return stops, segments


def build_scopes(stops, segments):
    core = {norm(n) for n in CONFIG["coreStops"]}
    by_seq = {s["seq"]: s for s in stops}
    core_idx = [g["idx"] for g in segments
                if norm(by_seq[g["fromSeq"]]["name"]) in core and norm(by_seq[g["toSeq"]]["name"]) in core]
    if not core_idx:
        notes.append("청라 중심부 구간을 정류장 이름으로 못 찾음 → coreStops 이름 확인")
    return [
        {"id": "all", "label": "노선 전체", "segmentIdx": [g["idx"] for g in segments], "turnaroundM": 0},
        {"id": "cheongna-core", "label": "청라 중심부", "segmentIdx": core_idx, "turnaroundM": None},
    ]


def day_type(ymd: str, dates) -> str | None:
    iso = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
    for t, lst in dates.items():
        if iso in lst:
            return t
    return None


# ---- 인천 대중교통 통계 API (ICPubTrans_v2) — 시간대 값이 hour00~hour23 열로 옆으로 온다
# data/raw/api/<op>/701_YYYYMMDD.json 에 원본 응답 저장 (fetch_api.py)
OPS = {
    "aboard": "BusAboardPsg_Route_InfoPage",   # 구간별 재차승객수: sequence(구간 순서), sectorName, hourNN
    "trips": "Bus_Route_BusStop_OPHour",       # 정류소별 운행횟수: busStopSeq, hourNN
    "runtime": "Bus_Route_Section_OPHour",      # 구간별 평균 운행시간: sectionName(순서 번호 없음), hourNN
    "ride": "BusRidePsg_Route_InfoPage",       # 정류소별 승차승객수: busStopSeq, hNNRidePsgCnt
}


def load_op(op, dates):
    """{dayType: [ (ymd, [items...]) ]}"""
    out = {"weekday": [], "holiday": []}
    for f in sorted((RAW / "api" / OPS[op]).glob(f"{CONFIG['routeNo']}_*.json")):
        ymd = f.stem.split("_")[-1]
        t = day_type(ymd, dates)
        if t:
            out[t].append((ymd, api_items(json.loads(f.read_text(encoding="utf-8")))))
    return out


def hour_val(item, h, op):
    k = f"h{h:02d}RidePsgCnt" if op == "ride" else f"hour{h:02d}"
    return num(item.get(k))


def mean_by(op, dates, key_fn):
    """날짜 평균: {(dayType, key, hour): value}"""
    res = {}
    for t, days in load_op(op, dates).items():
        if not days:
            continue
        acc = {}
        for _, items in days:
            for i, it in enumerate(items):
                k = key_fn(it, i)
                if k is None:
                    continue
                for h in range(24):
                    v = hour_val(it, h, op)
                    if v is not None:
                        acc[(k, h)] = acc.get((k, h), 0.0) + v
        for (k, h), v in acc.items():
            res[(t, k, h)] = v / len(days)
    return res


AGG = RAW / "api_agg_701.json"   # 브라우저/fetch_api 로 받은 날짜 평균 (dayType별)


def _agg():
    """평균을 nDays로 나눴는데 어떤 행이 그보다 적은 날에만 있었으면(daysSeen<nDays) 그 날수로 다시 맞춘다."""
    if not AGG.exists():
        return None
    A = json.loads(AGG.read_text(encoding="utf-8"))
    for t, a in A["agg"].items():
        for k, blk in a.items():
            if k == "runtime":
                continue  # 운행시간은 이미 값이 있는 날 평균
            for r in blk["rows"]:
                d = r.get("daysSeen") or blk["nDays"]
                if 0 < d < blk["nDays"]:
                    r["v"] = [v * blk["nDays"] / d for v in r["v"]]
    return A


def build_hourly(stops, segments, dates):
    """재차(구간 sequence) + 운행횟수(정류소 seq) + 운행시간(구간 이름)을 구간·시간대로 합친다."""
    A = _agg()
    if not A:
        notes.append("API 집계 파일 없음 → hourlySegments 비어 있음")
        return [], "sec", 0
    by_seq = {s["seq"]: s for s in stops}
    pair = lambda g: f"{by_seq[g['fromSeq']]['name']}~{by_seq[g['toSeq']]['name']}"
    out, dropped, unit = [], 0, "sec"
    for t, a in A["agg"].items():
        onb = {int(r["s"]): r["v"] for r in a["aboard"]["rows"] if r.get("s") not in (None, "", "-")}
        for r in a["aboard"]["rows"]:   # 구간 이름 검증
            i = int(r["s"]) - 1
            if 0 <= i < len(segments) and r["n"] != pair(segments[i]):
                notes.append(f"재차 구간 이름 불일치: sequence {r['s']} '{r['n']}' ≠ '{pair(segments[i])}'")
        trips = {int(r["s"]): r["v"] for r in a["trips"]["rows"] if str(r.get("s")).isdigit()}
        run = {}
        for r in a["runtime"]["rows"]:
            run.setdefault(r["n"], r["v"])
        missing_rt = [pair(g) for g in segments if pair(g) not in run]
        if missing_rt:
            notes.append(f"{t}: 운행시간 없는 구간 {len(missing_rt)}개 ({', '.join(missing_rt)})")
        for g in segments:
            # 구간 trips = 도착 정류장(toSeq)의 운행횟수. 기점(1번)은 출발·도착이 겹쳐 2배로 세지므로 쓰지 않음
            tv = trips.get(g["toSeq"]) or trips.get(g["fromSeq"])
            ov = onb.get(g["idx"] + 1)
            rv = run.get(pair(g))
            for h in range(24):
                tr = tv[h] if tv else 0.0
                o = ov[h] if ov else None
                if not tr and not o:
                    continue
                rt = rv[h] if rv and rv[h] else None
                spd = (g["distanceM"] / 1000) / (rt / 3600) if rt else None
                if spd is not None and not 3 <= spd <= 80:
                    notes.append(f"속도 이상값 제외: {t} {h}시 구간{g['idx']} {spd:.1f} km/h")
                    rt = spd = None
                    dropped += 1
                o_r = round(o, 1) if o is not None else None
                tr_r = round(tr, 2)
                out.append({
                    "dayType": t, "hour": h, "segmentIdx": g["idx"],
                    "onboard": o_r,
                    "trips": tr_r,
                    "runTimeSec": round(rt) if rt else None,
                    "avgLoad": round(o_r / tr_r, 1) if (o_r is not None and tr_r) else None,
                    "speedKmh": round(spd, 1) if spd else None,
                })
    return out, unit, dropped


def build_boardings(stops, hourly_segments, dates):
    A = _agg()
    if not A:
        notes.append("API 집계 파일 없음 → hourlyBoardings 비어 있음")
        return []
    out = []
    for t, a in A["agg"].items():
        rows = a["ride"]["rows"]
        for i, r in enumerate(rows):   # 정류소 순서 번호가 비어 있어 응답 순서 = seq 로 맞추고 이름으로 검증
            s = stops[i]
            if norm(r["n"]) != norm(s["name"]):
                notes.append(f"승차 정류장 이름 불일치: {i + 1}번째 '{r['n']}' ≠ '{s['name']}'")
                continue
            for h in range(24):
                if r["v"][h]:
                    out.append({"dayType": t, "hour": h, "stopSeq": s["seq"], "boardings": round(r["v"][h], 1)})
    return out


def avg_trip(segments, hs, hb):
    dist = {g["idx"]: g["distanceM"] for g in segments}
    res = {}
    for t in ("weekday", "holiday"):
        pm = sum((h["onboard"] or 0) * dist[h["segmentIdx"]] for h in hs if h["dayType"] == t)
        b = sum(x["boardings"] for x in hb if x["dayType"] == t)
        res[t] = round(pm / b) if b else None
    return res


def main():
    A = _agg()
    dates = A["dates"] if A else sample_dates()
    stops, segments = build_stops()
    scopes = build_scopes(stops, segments)
    hs, unit, dropped = build_hourly(stops, segments, dates)
    hb = build_boardings(stops, hs, dates)
    route = {
        "meta": {
            "routeNo": CONFIG["routeNo"], "operator": CONFIG["operator"],
            "isDummy": not hs,
            "sources": CONFIG["sources"],
            "sampleDates": dates,
        },
        "headwayMin": CONFIG["headwayMin"],
        "vehicleFuel": CONFIG["vehicleFuel"],
        "stops": stops,
        "segments": segments,
        "scopes": scopes,
        "hourlySegments": hs,
        "hourlyBoardings": hb,
        "avgTripM": avg_trip(segments, hs, hb),
        "quality": {
            "routeLengthM": sum(g["distanceM"] for g in segments),
            "officialTripsPerDay": CONFIG["officialTripsPerDay"],
            "runTimeUnit": unit, "droppedRows": dropped, "notes": notes,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(route, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: stops {len(stops)}, segments {len(segments)}, "
          f"hourlySegments {len(hs)}, hourlyBoardings {len(hb)}")
    for n in notes:
        print("  -", n)


if __name__ == "__main__":
    main()
