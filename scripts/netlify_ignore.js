#!/usr/bin/env node
/*
 * Netlify ignore command for credit-safe production deploys.
 *
 * Exit 0 => Netlify stops the build (no public-site change).
 * Exit 1 => Netlify continues the build.
 *
 * We deliberately fail open: if the diff cannot be determined, deploy.
 */
const { execFileSync } = require('node:child_process');

const from = process.env.CACHED_COMMIT_REF;
const to = process.env.COMMIT_REF;

function shouldPublish(path) {
  const exact = new Set([
    'index.html',
    'app.js',
    'styles.css',
    'favicon.svg',
    'robots.txt',
    'netlify.toml',
    'scripts/netlify_ignore.js',
    'scripts/restore_data.py',
    'scripts/build_rss.py',
  ]);
  if (exact.has(path)) return true;
  if (path.startsWith('data/')) return true;
  return false;
}

if (!from || !to) {
  console.log('Netlify ignore: missing commit refs; continue build.');
  process.exit(1);
}

try {
  const output = execFileSync('git', ['diff', '--name-only', from, to], { encoding: 'utf8' });
  const changed = output.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  const publicChanges = changed.filter(shouldPublish);

  console.log(`Netlify ignore: ${changed.length} changed file(s); ${publicChanges.length} publish-relevant.`);
  if (publicChanges.length) {
    console.log('Publish-relevant changes:', publicChanges.join(', '));
    process.exit(1);
  }

  console.log('Only CI/monitoring/docs changed; skip Netlify build.');
  process.exit(0);
} catch (error) {
  console.error('Netlify ignore: diff failed; continue build for safety.', error.message);
  process.exit(1);
}
