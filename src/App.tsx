import route from './data/route.json';
import assumptions from './data/assumptions.json';
import { simulate } from './lib/simulate';
import MapView from './components/MapView';
import CongestionChart from './components/CongestionChart';
import ScenarioPanel from './components/ScenarioPanel';
import ResultCard from './components/ResultCard';
import BreakEvenChart from './components/BreakEvenChart';
import AssumptionPanel from './components/AssumptionPanel';

export default function App() {
  // TODO: 시나리오·가정값 상태 → simulate() → 결과를 props로 전달
  const result = simulate(route, assumptions, {});

  return (
    <main>
      <MapView />
      <CongestionChart />
      <ScenarioPanel />
      <ResultCard />
      <BreakEvenChart />
      <AssumptionPanel />
    </main>
  );
}
