"""One-time migration from legacy artifacts; never trusts development/audit runs."""
import io, json, urllib.request, urllib.error, zipfile
from research_contract import fingerprint
API='https://api.github.com'
UA='MSNewsFetch-state-migration'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def github_headers(token: str) -> dict[str, str]:
    return {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': UA,
    }


def request_json(url: str, token: str):
    req = urllib.request.Request(url, headers=github_headers(token))
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def download_artifact(archive_url: str, token: str) -> bytes:
    """Follow GitHub's signed-storage redirect without leaking the GitHub auth header."""
    req = urllib.request.Request(archive_url, headers=github_headers(token))
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code not in (301, 302, 303, 307, 308):
            raise
        location = error.headers.get('Location')
        if not location:
            raise
    req = urllib.request.Request(location, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()



def restore_legacy(repo, token, mode):
    name = 'msnews-monitor-state' if mode == 'daily' else 'msnews-discovery-state'
    filename = 'state.json' if mode == 'daily' else 'discovery_state.json'
    data = request_json(f'{API}/repos/{repo}/actions/artifacts?name={name}&per_page=100', token)
    arts = sorted([a for a in data.get('artifacts', []) if not a.get('expired')], key=lambda a:a.get('created_at',''), reverse=True)
    for art in arts:
        run_info = art.get('workflow_run') or {}
        if run_info.get('head_branch') != 'main' or not run_info.get('id'):
            continue
        run = request_json(f'{API}/repos/{repo}/actions/runs/{run_info["id"]}', token)
        if run.get('conclusion') != 'success' or run.get('head_branch') != 'main':
            continue
        expected = '.github/workflows/research-monitor.yml' if mode == 'daily' else '.github/workflows/deep-discovery.yml'
        if run.get('path') != expected:
            continue
        payload = download_artifact(art['archive_download_url'], token)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            matches = [n for n in archive.namelist() if n.rsplit('/',1)[-1] == filename]
            if len(matches) != 1 or archive.getinfo(matches[0]).file_size > 25_000_000:
                raise ValueError('Invalid migration artifact')
            state = json.loads(archive.read(matches[0]))
        if not isinstance(state, dict) or 'version' not in state:
            raise ValueError('Invalid migration state')
        return state
    print('No trusted legacy journal: first successful scan will establish a silent baseline.')
    return None
