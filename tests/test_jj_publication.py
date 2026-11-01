"""Opt-in real jj/local-remote qualification; no hosted or private-product claim."""
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest


class JujutsuPublication(unittest.TestCase):
    def test_local_publication_and_git_managed_submodule(self):
        binary = os.environ.get('PATCHWERKS_JJ')
        if binary is None:
            self.skipTest('PATCHWERKS_JJ not supplied: real jj qualification unavailable')
        self.assertTrue(Path(binary).is_absolute() and Path(binary).is_file(), 'opt-in jj executable missing')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / 'home'; home.mkdir()
            config = root / 'jj.toml'
            config.write_text('[user]\nname = "Fixture"\nemail = "fixture@example.invalid"\n')
            git_binary = shutil.which('git')
            self.assertIsNotNone(git_binary, 'trusted Git executable required')
            env = {'PATH': str(Path(git_binary).parent) + ':/usr/bin:/bin', 'TMPDIR': str(root), 'HOME': str(home), 'XDG_CONFIG_HOME': str(home),
                   'JJ_CONFIG': str(config), 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
                   'GIT_AUTHOR_NAME': 'Fixture', 'GIT_AUTHOR_EMAIL': 'fixture@example.invalid',
                   'GIT_COMMITTER_NAME': 'Fixture', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid'}
            def run(*args, cwd=root, ok=True):
                result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=30)
                if ok: self.assertEqual(result.returncode, 0, result.stderr)
                return result
            def git(*args, cwd=root): return run(git_binary, *args, cwd=cwd).stdout.strip()
            def jj(*args, cwd=root, ok=True): return run(binary, '--no-pager', *args, cwd=cwd, ok=ok)
            jj('git', 'push', '--help')
            remote = root / 'remote.git'; git('init', '--bare', str(remote))
            work = root / 'work'; jj('git', 'clone', str(remote), str(work))
            (work / 'payload').write_text('first\n')
            jj('describe', '-m', 'synthetic publication', cwd=work)
            jj('bookmark', 'create', 'issue-6-fixture', '-r', '@', cwd=work)
            jj('git', 'push', '--remote', 'origin', '--bookmark', 'issue-6-fixture', cwd=work)
            head = jj('log', '--no-graph', '-r', 'issue-6-fixture', '-T', 'commit_id', cwd=work).stdout.strip()
            self.assertEqual(git('ls-remote', str(remote), 'refs/heads/issue-6-fixture').split()[0], head)
            writer = root / 'writer'; git('clone', '--branch', 'issue-6-fixture', str(remote), str(writer))
            (writer / 'other').write_text('second writer')
            git('add', '.', cwd=writer); git('commit', '-m', 'second writer', cwd=writer)
            git('push', 'origin', 'issue-6-fixture', cwd=writer)
            remote_head = git('rev-parse', 'HEAD', cwd=writer)
            (work / 'payload').write_text('stale rewrite\n')
            jj('describe', '-m', 'stale attempt', cwd=work)
            jj('bookmark', 'set', 'issue-6-fixture', '-r', '@', cwd=work)
            self.assertNotEqual(jj('git', 'push', '--remote', 'origin', '--bookmark', 'issue-6-fixture', cwd=work, ok=False).returncode, 0)
            self.assertEqual(git('ls-remote', str(remote), 'refs/heads/issue-6-fixture').split()[0], remote_head)
            # Independent synthetic Git-managed submodule; never run jj on its working tree.
            parent = root / 'parent'; git('init', str(parent))
            git('-c', 'protocol.file.allow=always', 'submodule', 'add', '-b', 'issue-6-fixture', str(remote), 'vendor/synthetic', cwd=parent)
            git('commit', '-am', 'synthetic submodule', cwd=parent)
            clone = root / 'parent-copy'; git('clone', str(parent), str(clone))
            git('-c', 'protocol.file.allow=always', 'submodule', 'update', '--init', cwd=clone)
            self.assertEqual(git('rev-parse', 'HEAD', cwd=clone / 'vendor/synthetic'), remote_head)
            self.assertEqual(git('ls-tree', 'HEAD', 'vendor/synthetic', cwd=clone).split()[0], '160000')


if __name__ == '__main__': unittest.main()
