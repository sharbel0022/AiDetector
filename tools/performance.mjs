import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { gzipSync } from 'node:zlib';
import { pathToFileURL } from 'node:url';
import { performance } from 'node:perf_hooks';
import { analyzeText, MAX_CHARS } from '../sites/src/analyzer.mjs';

export function percentile(values, fraction) {
  if (!Number.isFinite(fraction) || fraction <= 0 || fraction > 1) throw new RangeError('Percentile must be in (0, 1]');
  if (values.some(value => !Number.isFinite(value) || value < 0)) throw new RangeError('Durations must be finite and nonnegative');
  if (!values.length) return null;
  return [...values].sort((a,b) => a-b)[Math.ceil(values.length * fraction)-1];
}

export function summarizeDurations(values) {
  return {samples: values.length, p50Ms: percentile(values, 0.5), p95Ms: percentile(values, 0.95), maxMs: percentile(values, 1)};
}

export function checkBundleBudget(assets) {
  const jsGzipBytes = assets.filter(a => a.path.endsWith('.js')).reduce((sum,a) => sum+a.gzipBytes,0);
  const cssGzipBytes = assets.filter(a => a.path.endsWith('.css')).reduce((sum,a) => sum+a.gzipBytes,0);
  return {passed: jsGzipBytes <= 100_000 && cssGzipBytes <= 10_000, jsGzipBytes, cssGzipBytes, jsBudgetBytes:100_000, cssBudgetBytes:10_000};
}

function measure(text, language) {
  for (let i=0;i<10;i++) analyzeText(text, language);
  const durations=[];
  const rssBefore=process.memoryUsage().rss;
  for (let i=0;i<100;i++) {
    const start=performance.now();
    analyzeText(text, language);
    durations.push(performance.now()-start);
  }
  return {characters:text.length, language, ...summarizeDurations(durations), rssBeforeBytes:rssBefore, rssAfterBytes:process.memoryUsage().rss};
}

export function runPerformance(buildDir='dist') {
  const assetDir=path.join(buildDir,'assets');
  const assets=fs.readdirSync(assetDir).filter(name => /\.(?:js|css)$/.test(name)).map(name => {
    const data=fs.readFileSync(path.join(assetDir,name));
    return {path:name, bytes:data.length, gzipBytes:gzipSync(data).length};
  });
  if (!assets.some(a => a.path.endsWith('.js'))) throw new Error('Production JS bundle missing');
  const sv='Vi undersöker hur språket fungerar i olika sammanhang. En kort mening kan göra resonemanget tydligare, medan ett längre stycke ger plats åt nödvändiga förbehåll. Läsaren behöver kunna följa varje påstående tillbaka till originalets innehåll. ';
  const en='We examine how language works in different settings. A short sentence can clarify the reasoning, while a longer paragraph leaves room for necessary qualifications. The reader should be able to trace every claim back to the original material. ';
  const analysis=[];
  for (const [language, sample] of [['sv',sv],['en',en]]) {
    for (const length of [1000,6000,MAX_CHARS]) analysis.push(measure(sample.repeat(Math.ceil(length/sample.length)).slice(0,length),language));
  }
  return {measuredAt:new Date().toISOString(), environment:{node:process.version, platform:os.platform(), release:os.release(), cpu:os.cpus()[0]?.model, logicalCpus:os.cpus().length, physicalMemoryBytes:os.totalmem()}, assets, bundle:checkBundleBudget(assets), analysis, memoryNotice:'Process RSS samples include Node/runtime/GC and are not isolated analyzer allocation measurements.', modelColdStart:{status:'not_measured', reason:'Requires an available configured real model; no timing is inferred from mocks.'}};
}

if (process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href) {
  const report=runPerformance();
  fs.mkdirSync('artifacts',{recursive:true});
  fs.writeFileSync('artifacts/performance.json',JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
  if (!report.bundle.passed) process.exitCode=1;
}
