// Load scenarios of stage 1 (E16-05, prompt I5-02); k6 runs one of them:
//   k6 run -e SCENARIO=check|activate|race -e BASE_URL=... -e REQUESTS=dir/check.json scenario.js
// Requests are signed in advance by sign.py; iteration N sends request N at its second.
import http from 'k6/http';
import exec from 'k6/execution';
import { check } from 'k6';
import { SharedArray } from 'k6/data';

const SCENARIO = __ENV.SCENARIO;
const BASE_URL = __ENV.BASE_URL;
const RATE = Number(__ENV.RATE || (SCENARIO === 'check' ? 100 : 20));
const SECONDS = Number(__ENV.SECONDS || (SCENARIO === 'check' ? 900 : 600));
const RACE = Number(__ENV.RACE || 200);
const requests = new SharedArray('requests', () => JSON.parse(open(__ENV.REQUESTS)));

const scenarios = {
  check: {
    executor: 'constant-arrival-rate',
    rate: RATE,
    timeUnit: '1s',
    duration: `${SECONDS}s`,
    preAllocatedVUs: RATE * 2,
    maxVUs: RATE * 10,
  },
  activate: {
    executor: 'constant-arrival-rate',
    rate: RATE,
    timeUnit: '1s',
    duration: `${SECONDS}s`,
    preAllocatedVUs: RATE * 2,
    maxVUs: RATE * 10,
  },
  // 200 users activate one licence with limit = 100 at the same moment.
  race: { executor: 'per-vu-iterations', vus: RACE, iterations: 1, maxDuration: '2m' },
};

// Targets of section 15.6 of document 1 and of the prompt.
const thresholds = {
  check: { http_req_duration: ['p(95)<500'], http_req_failed: ['rate<0.001'] },
  activate: { http_req_duration: ['p(95)<500'], http_req_failed: ['rate<0.001'] },
  race: {},
};

export const options = {
  scenarios: { [SCENARIO]: scenarios[SCENARIO] },
  thresholds: thresholds[SCENARIO],
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export default function () {
  const index = SCENARIO === 'race' ? exec.vu.idInTest - 1 : exec.scenario.iterationInTest;
  const request = requests[index % requests.length];
  const response = http.post(`${BASE_URL}${request.path}`, request.body, {
    headers: { 'Content-Type': 'application/json', 'ALMI-Signature': request.signature },
    // A refused race activation (409 seats_exhausted) is an expected answer, not a failure.
    responseCallback: SCENARIO === 'race' ? http.expectedStatuses(201, 409) : http.expectedStatuses(200, 201),
    tags: { scenario: SCENARIO },
  });
  check(response, { answered: (r) => r.status !== 0 && r.status < 500 });
}
