// k6 부하 테스트 — 히트맵(서버 이미지 렌더=CPU)을 집중 호출해 HPA 오토스케일 유발.
//
// 사용법:
//   1) 이벤트 하나 만들고 EVENT_ID 확인 (URL의 /events/<여기>)
//   2) k6 run -e BASE_URL=https://YOUR_DOMAIN -e EVENT_ID=xxxx loadtest/script.js
//   3) 다른 창에서: watch kubectl get hpa,pods   → 파드가 늘어나는지 관찰!
import http from 'k6/http';
import { sleep } from 'k6';

export const options = {
  stages: [
    { duration: '1m', target: 20 },   // 워밍업
    { duration: '3m', target: 50 },   // 부하 유지 → CPU 상승 → 스케일 아웃
    { duration: '1m', target: 0 },    // 쿨다운 → 스케일 인
  ],
};

const BASE = __ENV.BASE_URL || 'http://localhost:8000';
const EVENT = __ENV.EVENT_ID || '';

export default function () {
  http.get(`${BASE}/events/${EVENT}/heatmap.png`);
  sleep(0.5);
}
