#!/usr/bin/env node
const assert = require('node:assert/strict');
const { shouldPublish, evaluateChangedFiles } = require('./netlify_ignore.js');

assert.equal(shouldPublish('index.html'), true);
assert.equal(shouldPublish('data/news.json.gz.part1'), true);
assert.equal(shouldPublish('scripts/build_rss.py'), true);
assert.equal(shouldPublish('scripts/monitor_research.py'), false);
assert.equal(shouldPublish('monitor/program_registry.json'), false);
assert.equal(shouldPublish('.github/workflows/research-monitor.yml'), false);
assert.equal(shouldPublish('README.md'), false);

assert.deepEqual(
  evaluateChangedFiles(['README.md', 'scripts/monitor_research.py', '.github/workflows/research-monitor.yml']),
  []
);
assert.deepEqual(
  evaluateChangedFiles(['README.md', 'styles.css', 'monitor/watchlist.json']),
  ['styles.css']
);

console.log('Netlify ignore tests: OK');
