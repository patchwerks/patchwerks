#!/usr/bin/env python3
"""Read-only observations, never an approval or publishing principal."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

LIMIT = 2 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(value):
    require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{40}', value), 'full lowercase Git SHA required')
    return value


def exact(obj, keys):
    require(isinstance(obj, dict) and set(obj) == set(keys), 'missing or unknown keys')


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError('nonfinite JSON rejected')


def read_json(path):
    path = Path(path).absolute()
    require(all(not part.is_symlink() for part in (path, *path.parents)), 'symlink JSON path rejected')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'regular JSON file required')
        data = stream.read(LIMIT + 1)
    require(len(data) <= LIMIT, 'JSON too large')
    return json.loads(data, object_pairs_hook=pairs, parse_constant=reject_constant)


def run(args, cwd=None):
    # Temporary files bound memory; file size limit also bounds subprocess output.
    import resource
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE, (LIMIT, LIMIT))
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        env = None
        if Path(args[0]).name == 'git':
            env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
            env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
                       GIT_NO_LAZY_FETCH='1', GIT_TERMINAL_PROMPT='0')
        result = subprocess.run(args, cwd=cwd, env=env, stdout=out, stderr=err,
                                timeout=30, check=False, preexec_fn=limits)
        require(result.returncode == 0, 'read-only command failed')
        out.seek(0)
        data = out.read(LIMIT + 1)
        require(len(data) <= LIMIT, 'command output too large')
        return data.decode('utf-8').strip()


def git(repo, *args):
    return run(['git', '--no-replace-objects', '-C', str(Path(repo).resolve()), *args])


def ref(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./-]{0,199}', value), 'invalid ref')
    require(not any(x in value for x in ('..', '//', '@{')) and not value.endswith(('/', '.', '.lock')), 'invalid ref')
    require(all(not x.startswith('.') and not x.endswith('.lock') for x in value.split('/')), 'invalid ref')
    return value


def repository(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', value), 'invalid GitHub repository')
    require(not value.endswith('.git'), 'repository identity must omit .git')
    return value


def publication(base_repository, head_repository, base_ref, head_ref, expected_head, number,
                expected_base, base_repository_id, head_repository_id):
    repository(base_repository); repository(head_repository)
    ref(base_ref); ref(head_ref); sha(expected_head); sha(expected_base)
    require(all(type(value) is int and value > 0 for value in (base_repository_id, head_repository_id)), 'invalid repository ID')
    require(type(number) is int and 0 < number < 1000000000, 'invalid PR number')
    route = f'repos/{base_repository}/pulls/{number}'
    def observe():
        pr = json.loads(run(['gh', 'api', '--hostname', 'github.com', '--method', 'GET', route]), object_pairs_hook=pairs, parse_constant=reject_constant)
        require(type(pr['number']) is int and pr['number'] == number, 'PR number mismatch')
        require(pr['state'] == 'open', 'PR is not open')
        for key, repo, branch, repo_id in [('base', base_repository, base_ref, base_repository_id), ('head', head_repository, head_ref, head_repository_id)]:
            require(type(pr[key]['repo']['id']) is int and pr[key]['repo']['id'] == repo_id, 'repository ID mismatch')
            require(pr[key]['repo']['full_name'] == repo and pr[key]['ref'] == branch, 'PR identity mismatch')
        require(pr['head']['sha'] == expected_head, 'PR head mismatch')
        require(pr['base']['sha'] == expected_base, 'PR base mismatch')
        remote = run(['git', '-c', 'credential.helper=', 'ls-remote', '--exit-code', '--refs',
                      f'https://github.com/{head_repository}.git', f'refs/heads/{head_ref}'])
        require(remote == f'{expected_head}\trefs/heads/{head_ref}', 'remote head mismatch')
        return (pr['base']['sha'], pr['head']['sha'], pr['updated_at'])
    first = observe()
    require(observe() == first, 'publication changed during observation')
    return {'publication_observed': True, 'execution_authorized': False, 'head': expected_head,
            'base_repository': base_repository, 'head_repository': head_repository, 'pr': number,
            'base': expected_base, 'base_repository_id': base_repository_id, 'head_repository_id': head_repository_id}


def inspect_release(repo, tag, accepted_commit, expected_tag_object, archive, digest, size):
    ref(tag); sha(accepted_commit); sha(expected_tag_object)
    require(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest), 'invalid SHA256')
    require(type(size) is int and 0 <= size <= 1024 ** 3, 'invalid bounded archive size')
    tagref = f'refs/tags/{tag}'
    require(git(repo, 'rev-parse', '--verify', tagref) == expected_tag_object, 'tag object changed')
    require(git(repo, 'cat-file', '-t', expected_tag_object) == 'tag', 'annotated tag required')
    header = git(repo, 'cat-file', '-p', expected_tag_object).split('\n\n', 1)[0].splitlines()
    require(header[:2] == [f'object {accepted_commit}', 'type commit'], 'tag must directly name accepted commit')
    require(git(repo, 'cat-file', '-t', accepted_commit) == 'commit', 'accepted object is not commit')
    for name in ('VERSION',):
        require(git(repo, 'cat-file', '-t', f'{accepted_commit}:{name}') == 'blob', 'VERSION must be blob')
    version = git(repo, 'show', f'{accepted_commit}:VERSION')
    path = Path(archive)
    require(path.is_absolute(), 'archive path must be absolute')
    require(all(not p.is_symlink() for p in (path, *path.parents)), 'symlink archive path rejected')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size == size, 'archive type/size mismatch')
        hasher = hashlib.sha256()
        remaining = size
        while remaining:
            chunk = stream.read(min(65536, remaining))
            require(chunk, 'archive truncated')
            remaining -= len(chunk); hasher.update(chunk)
        require(not stream.read(1), 'archive grew')
        after = os.fstat(stream.fileno())
        require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'archive changed')
    require(hasher.hexdigest() == digest, 'archive digest mismatch')
    require(git(repo, 'rev-parse', '--verify', tagref) == expected_tag_object, 'tag changed during inspection')
    return {'release_observed': True, 'execution_authorized': False, 'commit': accepted_commit,
            'tag_object': expected_tag_object, 'archive_sha256': digest, 'archive_size': size, 'version': version}


def plan_lock(current, proposal):
    exact(current, ('schema_version', 'kind', 'agentile', 'repositories', 'planned_components', 'private_metadata'))
    require(type(current['schema_version']) is int and current['schema_version'] == 1, 'unsupported schema')
    require(current['kind'] == 'integration-baseline-not-deployment-approval', 'invalid lock kind')
    exact(current['agentile'], ('repository', 'revision'))
    repository(current['agentile']['repository']); sha(current['agentile']['revision'])
    require(isinstance(current['private_metadata'], str), 'invalid private metadata')
    require(isinstance(current['planned_components'], list) and all(isinstance(x, str) for x in current['planned_components']), 'invalid components')
    require(isinstance(current['repositories'], list), 'invalid repositories')
    result = copy.deepcopy(current)
    enrolled = {}
    for item in result['repositories']:
        exact(item, ('id', 'repository', 'area', 'visibility', 'revision'))
        require(isinstance(item['id'], str) and re.fullmatch(r'[a-z][a-z0-9-]*', item['id']), 'invalid product ID')
        require(item['id'] not in enrolled, 'duplicate product ID')
        require(isinstance(item['area'], str) and item['visibility'] in ('public', 'private'), 'invalid metadata')
        repository(item['repository']); sha(item['revision']); enrolled[item['id']] = item
    exact(proposal, ('changes',))
    require(isinstance(proposal['changes'], list) and proposal['changes'], 'changes required')
    seen = set()
    for change in proposal['changes']:
        exact(change, ('id', 'old_revision', 'revision', 'tests', 'migration', 'rollback'))
        require(isinstance(change['id'], str) and change['id'] in enrolled and change['id'] not in seen, 'unknown/duplicate product')
        seen.add(change['id']); sha(change['old_revision']); sha(change['revision'])
        require(enrolled[change['id']]['revision'] == change['old_revision'], 'stale old revision')
        require(change['revision'] != change['old_revision'], 'unchanged revision')
        for key in ('tests', 'migration', 'rollback'):
            require(isinstance(change[key], str) and 0 < len(change[key]) <= 2048 and change[key].strip() == change[key], 'evidence reference required')
        enrolled[change['id']]['revision'] = change['revision']
    return (json.dumps(result, indent=2) + '\n').encode()


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'preflight failed: invalid command arguments\n')


def main():
    parser = SafeParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    pub = commands.add_parser('publication')
    for key in ('base-repository', 'head-repository', 'base-ref', 'head-ref', 'expected-head', 'expected-base'):
        pub.add_argument('--' + key, required=True)
    pub.add_argument('--number', type=int, required=True)
    pub.add_argument('--base-repository-id', type=int, required=True)
    pub.add_argument('--head-repository-id', type=int, required=True)
    release = commands.add_parser('release')
    for key in ('repo', 'tag', 'accepted-commit', 'expected-tag-object', 'archive', 'digest'):
        release.add_argument('--' + key, required=True)
    release.add_argument('--size', type=int, required=True)
    lock = commands.add_parser('lock')
    lock.add_argument('--current', required=True); lock.add_argument('--proposal', required=True)
    args = vars(parser.parse_args()); command = args.pop('command')
    try:
        if command == 'lock':
            import sys
            sys.stdout.buffer.write(plan_lock(read_json(args['current']), read_json(args['proposal'])))
        else:
            print(json.dumps((publication if command == 'publication' else inspect_release)(**args), sort_keys=True))
    except (ValueError, OSError, KeyError, TypeError, RecursionError, subprocess.SubprocessError):
        parser.exit(1, 'preflight failed: invalid input or observation\n')


if __name__ == '__main__':
    main()
