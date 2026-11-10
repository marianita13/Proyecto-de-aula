import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';

const BASE_URL = 'http://127.0.0.1:8000';
const LEVEL_DURATION = '15s';
const LEVEL_DURATION_SECONDS = 15;
const LEVEL_GAP_SECONDS = 2;
const FIRST_LEVEL_START_SECONDS = 10;

const levelStart = (index) =>
  `${FIRST_LEVEL_START_SECONDS + index * (LEVEL_DURATION_SECONDS + LEVEL_GAP_SECONDS)}s`;

export const options = {
  summaryTrendStats: ['avg', 'min', 'max', 'p(95)'],
  scenarios: {
    warmup: {
      executor: 'constant-vus',
      vus: 1,
      duration: '8s',
      exec: 'warmup',
      tags: { load_level: 'warmup' },
    },
    level_1: {
      executor: 'constant-vus',
      vus: 1,
      duration: LEVEL_DURATION,
      startTime: levelStart(0),
      exec: 'measure',
      tags: { load_level: '1' },
    },
    level_2: {
      executor: 'constant-vus',
      vus: 2,
      duration: LEVEL_DURATION,
      startTime: levelStart(1),
      exec: 'measure',
      tags: { load_level: '2' },
    },
    level_4: {
      executor: 'constant-vus',
      vus: 4,
      duration: LEVEL_DURATION,
      startTime: levelStart(2),
      exec: 'measure',
      tags: { load_level: '4' },
    },
    level_8: {
      executor: 'constant-vus',
      vus: 8,
      duration: LEVEL_DURATION,
      startTime: levelStart(3),
      exec: 'measure',
      tags: { load_level: '8' },
    },
    level_12: {
      executor: 'constant-vus',
      vus: 12,
      duration: LEVEL_DURATION,
      startTime: levelStart(4),
      exec: 'measure',
      tags: { load_level: '12' },
    },
    level_24: {
      executor: 'constant-vus',
      vus: 24,
      duration: LEVEL_DURATION,
      startTime: levelStart(5),
      exec: 'measure',
      tags: { load_level: '24' },
    },
    level_48: {
      executor: 'constant-vus',
      vus: 48,
      duration: LEVEL_DURATION,
      startTime: levelStart(6),
      exec: 'measure',
      tags: { load_level: '48' },
    },
    level_96: {
      executor: 'constant-vus',
      vus: 96,
      duration: LEVEL_DURATION,
      startTime: levelStart(7),
      exec: 'measure',
      tags: { load_level: '96' },
    },
  },
};

function requestWork() {
  const loadLevel = exec.scenario.name.replace('level_', '');
  const response = http.get(`${BASE_URL}/work`, {
    tags: { load_level: loadLevel },
  });

  check(response, {
    'respondió con HTTP 200': (result) => result.status === 200,
  });
}

export function warmup() {
  const response = http.get(`${BASE_URL}/work`, {
    tags: { load_level: 'warmup' },
  });
  check(response, {
    'el endpoint de trabajo está disponible': (result) => result.status === 200,
  });
}

export function measure() {
  requestWork();
}
