"""
인천 대중교통 통계 API (ICPubTrans_v2) 수집 — 701번, 2026년 9월
  scripts/.env 에 DATA_GO_KR_KEY=<공공데이터포털 일반 인증키(Decoding)>
  python scripts/fetch_api.py --probe        # 9/1 하루만 받아 필드 확인
  python scripts/fetch_api.py                # sampleDates 전체 (4개 기능 × 27일 = 108회)
결과: data/raw/api/<기능>/701_YYYYMMDD.json
"""
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from build_route import CONFIG, OPS, RAW, ROOT, sample_dates  # noqa: E402

BASE = "https://apis.data.go.kr/6280000/ICPubTrans_v2"


def key():
    env = ROOT / "scripts" / ".env"
    for line in env.read_text(encoding="utf-8").splitlines() if env.exists() else []:
        if line.startswith("DATA_GO_KR_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("scripts/.env 에 DATA_GO_KR_KEY 를 넣으세요")


def get(op, ymd):
    params = {"serviceKey": key(), "pageNo": 1, "numOfRows": 1000, "YMD": ymd, "routeName": CONFIG["routeNo"]}
    r = requests.get(f"{BASE}/{op}", params=params, timeout=30)
    r.raise_for_status()
    try:
        return r.json()
    except ValueError:
        sys.exit(f"{op} {ymd}: JSON이 아닌 응답 → {r.text[:300]}")


def main():
    probe = "--probe" in sys.argv
    days = ["20260901"] if probe else [d.replace("-", "") for t in ("weekday", "holiday") for d in sample_dates()[t]]
    for ymd in days:
        for op in OPS.values():
            out = RAW / "api" / op / f"{CONFIG['routeNo']}_{ymd}.json"
            if out.exists() and not probe:
                continue
            data = get(op, ymd)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            hdr = (data.get("response", data).get("header") or {})
            print(ymd, op, hdr.get("resultCode"), hdr.get("resultMsg"))
            time.sleep(0.3)


if __name__ == "__main__":
    main()
