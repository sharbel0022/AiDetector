import test from 'node:test';
import assert from 'node:assert/strict';
import { percentile, summarizeDurations, checkBundleBudget } from './performance.mjs';

test('latency report uses nearest-rank percentiles without dropping slow outliers', () => {
  const report = summarizeDurations([1, 2, 3, 4, 100]);
  assert.deepEqual(report, {samples: 5, p50Ms: 3, p95Ms: 100, maxMs: 100});
  assert.equal(percentile([4, 1, 2, 3], 0.5), 2);
  assert.deepEqual(summarizeDurations([]), {samples: 0, p50Ms: null, p95Ms: null, maxMs: null});
});

test('invalid timing values cannot produce a reassuring performance report', () => {
  for (const value of [NaN, Infinity, -1]) assert.throws(() => summarizeDurations([value]));
  assert.throws(() => percentile([1], 2));
});

test('bundle gate fails when aggregate JavaScript or CSS gzip budgets are exceeded', () => {
  assert.equal(checkBundleBudget([{path:'a.js', gzipBytes:60_000}, {path:'b.js', gzipBytes:50_000}]).passed, false);
  assert.equal(checkBundleBudget([{path:'a.css', gzipBytes:10_001}]).passed, false);
  assert.equal(checkBundleBudget([{path:'a.js', gzipBytes:90_000}, {path:'a.css', gzipBytes:9_000}]).passed, true);
});
