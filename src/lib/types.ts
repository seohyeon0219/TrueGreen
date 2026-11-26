// src/lib/types.ts
// 배차 추가 시뮬레이터 데이터 설계 (초안)
// - route.json, assumptions.json 의 모양과 simulate() 입출력을 정의한다.
// - "TBD" 주석 = 팀 확인 전. 확정되면 주석을 지운다.
//
// 단위 규칙 (파일 전체 공통)
//   거리: m (원본 구간거리가 m)       시간: 초(sec)        배차간격: 분(min)
//   승차·재차: 통행(건) — 사람 수가 아니라 승차 횟수
//   운행: 회                          탄소: kgCO2
//   시간대: hour 0–23, 1시간 단위 (회의 결정)

/* ───────────────────────── route.json ───────────────────────── */

export type DayType = "weekday" | "holiday"; // 평일 / 공휴일(휴일)

export type RouteData = {
  meta: {
    routeNo: string;            // "701"
    operator: string;           // "인천교통공사"
    isDummy: boolean;           // 더미값이면 true (API 데이터 받기 전)
    sources: {
      stops: string;            // 정류장·구간거리 출처 + 기준일
      coords: string;           // 좌표 출처 + 기준일
      headway: string;          // 배차간격 출처 + 기준일
      hourly: string;           // 재차·운행횟수·승차 출처
    };
    // TBD(현승): 평일/휴일 대표값을 어떤 날짜로 만들지 (예: 평일 5일 평균)
    sampleDates: Record<DayType, string[]>;
  };

  // 현재 배차간격 (분). 출처: 인천시 시내버스 노선현황
  // TBD(현승): 노선현황에 휴일 배차가 따로 있는지 미확인 → 없으면 holiday = null
  headwayMin: Record<DayType, number | null>;

  // TBD(태동): 701번 차량 연료 미확인. 버스 배출계수 선택에 필요
  vehicleFuel: "diesel" | "cng" | "electric" | "hydrogen" | null;

  stops: Stop[];
  segments: Segment[];

  // 메뉴에서 고를 적용 구간 목록. "노선 전체"는 항상 포함
  scopes: Scope[];

  hourlySegments: HourlySegment[];
  hourlyBoardings: HourlyBoarding[];

  // [실측값] 승객 평균 승차거리 (m), 현승 계산
  // = Σ(구간 재차승객수 × 구간거리) ÷ Σ(승차 건수), 같은 dayType의 하루 전체 기준
  // assumptions.json의 carTripM(대체되는 승용차 주행거리) 기본값으로 사용
  avgTripM: Record<DayType, number | null>;

  // [실측값] 정류장별 회차 거리 (m), 현승 측정 — 카카오맵 자동차 길찾기
  // 구간만 추가 운행할 때 구간 끝 정류장에서 반대 방향 정류장까지 돌아가는 거리
  turnarounds: Turnaround[];
};

export type Turnaround = {
  stopName: string;
  upStopSeq: number;            // 상행 정류장 seq (stops와 연결)
  downStopSeq: number;          // 하행 정류장 seq
  upToDownM: number;            // 상행 정류장 → 유턴 → 하행 정류장
  downToUpM: number;            // 하행 정류장 → 유턴 → 상행 정류장
};

export type Stop = {
  seq: number;                  // 노선 내 순서 (1부터)
  stopId: string;               // 정류소아이디 (노선↔좌표 연결 키)
  stopNo: string;               // 정류소번호 (노선↔승객 CSV 연결 키)
  name: string;
  lat: number;                  // 주의: 원본 CSV는 위도·경도 열 이름이 바뀌어 있음
  lng: number;
  // 9/30 하루 승하차 건수, 모든 노선 합계 → 지도 참고용. 계산에 쓰지 않음
  dailyOnOffAllRoutes: number | null;
};

export type Segment = {
  idx: number;                  // 0부터
  fromSeq: number;
  toSeq: number;
  distanceM: number;            // 구간거리 (m)
};

export type Scope = {
  id: string;                   // "all", "cheongna-core"
  label: string;                // 메뉴에 보일 이름
  segmentIdx: number[];         // 포함 구간
  // TBD(태동): 구간만 추가 운행할 때 회차 거리 가정 (m). "all"이면 0
  turnaroundM: number | null;
};

export type HourlySegment = {
  dayType: DayType;
  hour: number;                 // 0–23
  segmentIdx: number;
  onboard: number;              // 구간 재차승객수 (통행)
  trips: number;                // 운행횟수 (회)
  // TBD(현승 확인 → 태동 결정): 운행 1회가 왕복인지 한 방향인지. 계산 1·2단계 거리 기준
  // 구간 운행시간 (초). API 단위 미확인(현승 확인) → 전처리에서 초로 변환
  runTimeSec: number | null;

  // [실측값] 현승 계산
  avgLoad: number | null;       // 버스 1대당 평균 탑승 인원 = onboard ÷ trips (통행/회)
  speedKmh: number | null;      // 구간 운행 속도 = (distanceM ÷ 1000) ÷ (runTimeSec ÷ 3600)
};

export type HourlyBoarding = {
  dayType: DayType;
  hour: number;
  stopSeq: number;
  boardings: number;            // 승차 건수 (통행), 701번만
};

/* ─────────────────────── assumptions.json ────────────────────── */

export type AssumptionStatus = "실측" | "원문 확인" | "가정" | "미확인";

export type Assumption<T = unknown> = {
  key: string;
  label: string;
  value: T | null;              // 아직 값이 없으면 null
  unit: string;
  adjustable: boolean;          // 메뉴에서 바꿀 수 있는지
  source: string;
  status: AssumptionStatus;
  note?: string;                // 적용 조건, 한계
};

// 탄력성은 현재 배차간격 구간별로 값이 다름
export type ElasticityBand = {
  minHeadwayMin: number | null; // 이상 (null = 하한 없음)
  maxHeadwayMin: number | null; // 미만 또는 이하 (inclusiveMax 참고)
  inclusiveMax: boolean;
  value: number;
};

export type Assumptions = {
  shiftRatio: Assumption<number[]>;               // [0.33, 0.5]
  headwayElasticity: Assumption<ElasticityBand[]>;
  elasticityMethod: Assumption<"approx" | "midpoint">; // TBD(태동)
  carOccupancy: Assumption<number>;               // 인/대
  carTripM: Assumption<number>;                   // 대체되는 승용차 주행거리 (m)
  carSpeedKmh: Assumption<Record<"amPeak" | "offPeak" | "pmPeak", number>>;
  carSpeedHours: Assumption<Record<"amPeak" | "offPeak" | "pmPeak", number[]>>; // TBD(태동)
  busEmissionFactor: Assumption<EmissionFactor>;
  carEmissionFactor: Assumption<EmissionFactor>;
  weatherEffect: Assumption<unknown>;             // TBD(태동): 계산 방법 미정
};

// TBD(태동): 국가 배출계수 원 계수표 확인 후 식의 형태 확정
// 예: 속도 구간별 g/km 표, 또는 a·V^b 같은 식
export type EmissionFactor = {
  form: "table" | "formula" | null;
  table?: { minKmh: number; maxKmh: number; gPerKm: number }[];
  formula?: { expression: string; coefficients: Record<string, number> };
};

/* ─────────────────────── simulate() 입출력 ───────────────────── */
// TBD(태동): 계산식 확정 후 최종 확정. simulate.ts 작성자는 팀 결정 필요

export type Scenario = {
  dayType: DayType;
  hours: number[];              // 적용 시간대 (0–23)
  scopeId: string;              // Scope.id
  newHeadwayMin: number;        // 변경 배차간격 (분)
  // 메뉴에서 바꾼 가정값. 없으면 assumptions.json 기본값
  overrides: {
    shiftRatio?: number;
    elasticity?: number;
    carTripM?: number;
  };
  weather?: "normal" | "hot";   // TBD(태동)
};

export type Result = {
  // 단계별 중간값 (화면의 수식 설명·검증용)
  addedTrips: number;           // 1. 추가 운행횟수 (회/일)
  addedBusKm: number;           // 2. 추가 주행거리 (km/일)
  addedBusKg: number;           // 3. 늘어난 버스 탄소 (kgCO2/일)
  ridershipChangeRate: number;  // 4. 승객 증가율 (비율, 0.153 = 15.3%)
  addedRiders: number;          // 5. 늘어난 승객 (통행/일)
                                //    TBD(태동): "현재 승차" 범위 = 적용 구간 정류장·적용 시간대 승차만 셀지
  carTripsAvoided: number;      // 6. 줄어든 차 운행 (회/일)
  avoidedCarKg: number;         // 7. 줄어든 차 탄소 (kgCO2/일)
  netKg: number;                // 8. 순변화 = 3 − 7 (음수면 감소)

  // 기능명세서 "보여줄 것"
  // TBD(태동): 범위 = "적용 범위 버스 운행 + 버스로 옮겨올 승용차 이동" (제안, 미확정)
  currentBusKg: number;         // 적용 범위 현재 버스 탄소
  baselineKg: number;           // 원래 = currentBusKg + avoidedCarKg
  afterKg: number;              // 변경 후 = currentBusKg + addedBusKg
  reducedKg: number;            // 줄어든 양 = baselineKg − afterKg (음수 가능)

  // 손익분기 = addedBusKg ÷ (전환 비율 100%일 때 avoidedCarKg)
  breakEvenRatio: number | null; // 차 탄소가 0이면 null
  breakEvenOver100: boolean;     // true면 "전부 차에서 와도 탄소 증가"
};