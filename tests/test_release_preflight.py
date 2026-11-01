import copy
from unittest.mock import patch
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('release_preflight', Path(__file__).resolve().parents[1] / 'scripts/release_preflight.py')
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(self.root),
                    'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
                    'GIT_AUTHOR_NAME': 'Fixture', 'GIT_AUTHOR_EMAIL': 'fixture@example.invalid',
                    'GIT_COMMITTER_NAME': 'Fixture', 'GIT_COMMITTER_EMAIL': 'fixture@example.invalid'}
        self.repo = self.root / 'repo'; self.repo.mkdir()
        self.g('init', '-q')
        (self.repo / 'VERSION').write_text('1.0.0\n')
        self.g('add', 'VERSION'); self.g('commit', '-qm', 'fixture')
        self.commit = self.g('rev-parse', 'HEAD')
        self.g('tag', '-a', 'v1', '-m', 'release')
        self.tag = self.g('rev-parse', 'refs/tags/v1')
        self.archive = self.root / 'artifact.tar'; self.archive.write_bytes(b'opaque archive bytes')
        self.digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def g(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], env=self.env, stderr=subprocess.PIPE).decode().strip()

    def inspect(self, **kwargs):
        args = dict(repo=self.repo, tag='v1', accepted_commit=self.commit, expected_tag_object=self.tag,
                    archive=self.archive, digest=self.digest, size=self.archive.stat().st_size)
        args.update(kwargs)
        return p.inspect_release(**args)

    def test_annotated_and_dirty_worktree_independent(self):
        (self.repo / 'VERSION').write_text('dirty')
        self.assertEqual(self.inspect()['version'], '1.0.0')
        self.assertFalse(self.inspect()['execution_authorized'])

    def test_retag_and_lightweight_rejected(self):
        self.g('tag', '-f', '-a', 'v1', '-m', 'different')
        with self.assertRaises(ValueError): self.inspect()
        self.g('tag', '-f', 'v1', self.commit)
        with self.assertRaises(ValueError): self.inspect(expected_tag_object=self.commit)

    def test_replacement_refs_ignored(self):
        (self.repo / 'VERSION').write_text('9.0.0')
        self.g('commit', '-qam', 'replacement')
        self.g('replace', self.commit, self.g('rev-parse', 'HEAD'))
        self.assertEqual(self.inspect()['version'], '1.0.0')

    def test_bad_archive(self):
        with self.assertRaises(ValueError): self.inspect(digest='0' * 64)
        with self.assertRaises(ValueError): self.inspect(size=True)
        link = self.root / 'link'; link.symlink_to(self.archive)
        with self.assertRaises(ValueError): self.inspect(archive=link)

    def test_blob_required(self):
        (self.repo / 'VERSION').unlink(); (self.repo / 'VERSION').mkdir()
        (self.repo / 'VERSION' / 'nested').write_text('x')
        self.g('add', '-A'); self.g('commit', '-qm', 'tree')
        self.g('tag', '-fa', 'v1', '-m', 'tree tag')
        with self.assertRaises(ValueError):
            self.inspect(accepted_commit=self.g('rev-parse', 'HEAD'), expected_tag_object=self.g('rev-parse', 'v1'))


class LockTests(unittest.TestCase):
    def setUp(self):
        self.lock = dict(schema_version=1, kind='integration-baseline-not-deployment-approval',
                         agentile=dict(repository='example/framework', revision='a'*40),
                         repositories=[dict(id='synthetic', repository='example/synthetic', area='Test', visibility='public', revision='b'*40)],
                         planned_components=[], private_metadata='retain')
        self.change = dict(id='synthetic', old_revision='b'*40, revision='c'*40, tests='evidence/tests', migration='evidence/migration', rollback='evidence/rollback')

    def test_revision_only_and_rollback(self):
        proposed = json.loads(p.plan_lock(self.lock, {'changes': [self.change]}))
        self.assertEqual(self.lock['repositories'][0]['revision'], 'b'*40)
        self.assertEqual(proposed['repositories'][0]['revision'], 'c'*40)
        reverse = dict(self.change, old_revision='c'*40, revision='b'*40)
        self.assertEqual(json.loads(p.plan_lock(proposed, {'changes': [reverse]})), self.lock)

    def test_strict_inputs(self):
        for mutation in ({'old_revision': 'd'*40}, {'id': 'unknown'}, {'rollback': ''}, {'version': '2'}, {'revision': True}):
            with self.assertRaises(ValueError): p.plan_lock(self.lock, {'changes': [dict(self.change, **mutation)]})
        with self.assertRaises(ValueError): p.plan_lock(self.lock, {'changes': [self.change, self.change]})
        with self.assertRaises(ValueError): p.plan_lock(dict(self.lock, schema_version=True), {'changes': [self.change]})
        with self.assertRaises(ValueError): json.loads('{"x":1,"x":2}', object_pairs_hook=p.pairs)

    def test_bad_publication_inputs_fail_before_commands(self):
        with self.assertRaises(ValueError): p.publication('bad/../repo', 'a/b', 'main', 'topic', 'a'*40, 1, 'b'*40, 10, 20)
        with self.assertRaises(ValueError): p.publication('a/b', 'a/b', 'main', '--help', 'a'*40, 1, 'b'*40, 10, 20)
        with self.assertRaises(ValueError): p.publication('a/b', 'a/b', 'main', 'topic', 'a'*40, True, 'b'*40, 10, 20)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.pr = {'number': 6, 'state': 'open', 'updated_at': 'stable',
                   'base': {'repo': {'full_name': 'example/base', 'id': 10}, 'ref': 'main', 'sha': 'a'*40},
                   'head': {'repo': {'full_name': 'example/fork', 'id': 20}, 'ref': 'topic', 'sha': 'b'*40}}
        self.remote = 'b'*40 + '\trefs/heads/topic'

    def observe(self, values):
        with patch.object(p, 'run', side_effect=values) as transport:
            result = p.publication('example/base', 'example/fork', 'main', 'topic', 'b'*40, 6, 'a'*40, 10, 20)
            calls = transport.call_args_list
        return result, calls

    def test_exact_success_routes(self):
        result, calls = self.observe([json.dumps(self.pr), self.remote] * 2)
        self.assertTrue(result['publication_observed'])
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(result['base'], 'a'*40)
        self.assertEqual(result['head_repository_id'], 20)
        self.assertEqual(calls[0].args[0], ['gh', 'api', '--hostname', 'github.com', '--method', 'GET', 'repos/example/base/pulls/6'])
        self.assertEqual(calls[1].args[0][-2:], ['https://github.com/example/fork.git', 'refs/heads/topic'])
        self.assertEqual(calls[0], calls[2])
        self.assertEqual(calls[1], calls[3])

    def test_wrong_identity_and_stale_revisions(self):
        variants = []
        for side, field, value in [('base', 'sha', 'c'*40), ('head', 'sha', 'c'*40)]:
            item = copy.deepcopy(self.pr); item[side][field] = value; variants.append(item)
        for side in ('base', 'head'):
            item = copy.deepcopy(self.pr); item[side]['repo']['id'] = 99; variants.append(item)
        item = copy.deepcopy(self.pr); item['number'] = 7; variants.append(item)
        for item in variants:
            with self.assertRaises(ValueError): self.observe([json.dumps(item), self.remote])

    def test_changed_between_readbacks(self):
        item = copy.deepcopy(self.pr); item['updated_at'] = 'changed'
        with self.assertRaises(ValueError):
            self.observe([json.dumps(self.pr), self.remote, json.dumps(item), self.remote])
        with self.assertRaises(ValueError):
            self.observe([json.dumps(self.pr), self.remote, json.dumps(self.pr), 'c'*40 + '\trefs/heads/topic'])

    def test_regular_bounded_strict_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.json'
            for text in ('{"x":NaN}', '{"x":Infinity}', '{"x":1,"x":2}'):
                path.write_text(text)
                with self.assertRaises(ValueError): p.read_json(path)
            link = Path(directory) / 'link'; link.symlink_to(path)
            with self.assertRaises(ValueError): p.read_json(link)
            fifo = Path(directory) / 'fifo'; os.mkfifo(fifo)
            with self.assertRaises(ValueError): p.read_json(fifo)


if __name__ == '__main__': unittest.main()
