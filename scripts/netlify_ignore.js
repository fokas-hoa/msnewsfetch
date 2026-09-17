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

const PUBLISH_EXACT = new Set([
  'index.html',
  'app.js',
  'styles.css',
  'favicon.svg',
  'robots.txt',
  'netlify.toml',
  'scripts/netlify_ignore.js',
  'scripts/restore_data.py',
  'scripts/build_rss.py',
  'scripts/build_site.py',
  'scripts/baseline_identity.py',
  'scripts/research_contract.py',
]);

function shouldPublish(path) {
  if (PUBLISH_EXACT.has(path)) return true;
  if (path.startsWith('data/')) return true;
  return false;
}

function evaluateChangedFiles(changed) {
  return changed.filter(shouldPublish);
}

function main() {
  if(process.env.BRANCH==='live-data') return 0;
  if(process.env.MSNEWS_FORCE_BUILD==='1') return 1;
  const from = process.env.CACHED_COMMIT_REF;
  const to = process.env.COMMIT_REF;

  if (!from || !to || from===to) {
    console.log('Netlify ignore: missing commit refs; continue build.');
    return 1;
  }

  try {
    const output = execFileSync('git', ['diff', '--name-only', from, to], { encoding: 'utf8' });
    const changed = output.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
    const publicChanges = evaluateChangedFiles(changed);

    console.log(`Netlify ignore: ${changed.length} changed file(s); ${publicChanges.length} publish-relevant.`);
    if (publicChanges.length) {
      console.log('Publish-relevant changes:', publicChanges.join(', '));
      return 1;
    }

    console.log('Only CI/monitoring/docs changed; skip Netlify build.');
    return 0;
  } catch (error) {
    console.error('Netlify ignore: diff failed; continue build for safety.', error.message);
    return 1;
  }
}

module.exports = { shouldPublish, evaluateChangedFiles, main };

if (require.main === module) {
  process.exit(main());
}
