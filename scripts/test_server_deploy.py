"""Run on Linux: python3 scripts/test_server_deploy.py. No live site is touched."""
import functools
import hashlib
import http.server
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import threading
import unittest

from server_deploy import Deployer, digest


ID = "20260928-160000-001-a5defca"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if getattr(self.server, 'fail_search', False) and self.path.startswith('/search-data.json?'):
            self.send_error(404)
            return
        super().do_GET()


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="jla-deploy-test-")
        self.root = Path(self.temp.name)
        self.old = self.root / "releases" / "old"
        self.old.mkdir(parents=True)
        self.before = {"index.html": b"old home", "index.json": b"[]",
                       "events/index.html": b"events", "news/index.html": b"news",
                       "music/song.mp3": b"unchanged music", "removed.html": b"old"}
        for name, content in self.before.items():
            p = self.old / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
        (self.root / "current").symlink_to(self.old, target_is_directory=True)
        self.after = {k: v for k, v in self.before.items() if k != "removed.html"}
        self.after.update({"index.html": b"new home", "events/recruit/index.html": b"new event",
                           "image/招新/写真.png": b"unicode asset"})
        handler = functools.partial(QuietHandler, directory=str(self.root / "current"))
        self.http = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.deployer = Deployer(self.root, "http://127.0.0.1:" + str(self.http.server_port))

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.temp.cleanup()

    def make_plan(self, after=None, checks=None):
        after = self.after if after is None else after
        self.deployer.begin(ID)
        incoming = self.deployer.paths(ID)[1]
        manifest = {"schema": 1, "commit": "a" * 40, "files": {
            name: {"size": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            for name, content in after.items()}}
        if checks is not None:
            manifest["check_files"] = checks
        (incoming / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return self.deployer.plan(ID)

    def archive(self, plan, unsafe=False):
        path = self.deployer.paths(ID)[1] / "delta.tar.gz"
        with tarfile.open(path, "w:gz", format=tarfile.PAX_FORMAT) as tar:
            if unsafe:
                item = tarfile.TarInfo("../escape")
                item.size = 1
                tar.addfile(item, io.BytesIO(b"x"))
            else:
                for name in plan["needed"]:
                    data = self.after[name]
                    item = tarfile.TarInfo(name)
                    item.size = len(data)
                    tar.addfile(item, io.BytesIO(data))
        return digest(path)

    def test_prepare_publish_rollback_and_hardlinks(self):
        old_hashes = {n: digest(self.old / n) for n in self.before}
        plan = self.make_plan()
        self.assertNotIn("music/song.mp3", plan["needed"])
        self.deployer.prepare(ID, self.archive(plan))
        release = self.deployer.paths(ID)[3]
        self.assertEqual(self.deployer.current(), self.old)
        self.assertTrue(os.path.samefile(self.old / "music/song.mp3", release / "music/song.mp3"))
        self.assertFalse(os.path.samefile(self.old / "index.html", release / "index.html"))
        self.assertFalse((release / "removed.html").exists())
        self.assertEqual((release / "image/招新/写真.png").read_bytes(), b"unicode asset")
        self.assertFalse(self.deployer.paths(ID)[1].exists())
        self.deployer.publish(ID)
        self.assertEqual(self.deployer.current(), release)
        self.deployer.rollback(ID)
        self.assertEqual(self.deployer.current(), self.old)
        self.assertEqual(old_hashes, {n: digest(self.old / n) for n in self.before})

    def test_failed_http_check_restores_previous(self):
        plan = self.make_plan()
        self.deployer.prepare(ID, self.archive(plan))
        self.deployer.base_url += "/unavailable"
        with self.assertRaisesRegex(ValueError, "previous release restored"):
            self.deployer.publish(ID)
        self.assertEqual(self.deployer.current(), self.old)
        self.assertEqual(self.deployer.state(ID)["phase"], "rolled_back")

    def test_json_health_check_publish_and_rollback(self):
        self.after['search-data.json'] = b'[{"title":"song"}]'
        self.make_plan(checks=['index.html', 'search-data.json'])
        state = self.deployer.state(ID)
        self.assertIn('search-data.json', state['checks'])
        self.deployer.prepare(ID, self.archive(state))
        self.deployer.publish(ID)
        self.assertEqual(self.deployer.state(ID)['phase'], 'published')
        self.deployer.rollback(ID)
        self.assertEqual(self.deployer.current(), self.old)

    def test_failed_json_health_check_restores_previous(self):
        self.after['search-data.json'] = b'[]'
        plan = self.make_plan(checks=['search-data.json'])
        self.deployer.prepare(ID, self.archive(plan))
        # The homepage stays accessible while only the JSON HTTP route fails.
        self.http.fail_search = True
        with self.assertRaisesRegex(ValueError, 'previous release restored'):
            self.deployer.publish(ID)
        self.assertEqual(self.deployer.current(), self.old)

    def test_health_check_rejects_missing_files(self):
        with self.assertRaisesRegex(ValueError, 'generated HTML or JSON'):
            self.make_plan(checks=['missing.json'])

    def test_health_check_rejects_non_document_files(self):
        with self.assertRaisesRegex(ValueError, 'generated HTML or JSON'):
            self.make_plan(checks=['music/song.mp3'])

    def test_bad_checksum_cannot_change_current(self):
        plan = self.make_plan()
        self.archive(plan)
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.deployer.prepare(ID, "0" * 64)
        self.assertEqual(self.deployer.current(), self.old)

    def test_archive_path_traversal_is_rejected(self):
        plan = self.make_plan()
        with self.assertRaisesRegex(ValueError, "Unsafe file path"):
            self.deployer.prepare(ID, self.archive(plan, unsafe=True))
        self.assertFalse(self.deployer.paths(ID)[2].exists())
        self.assertEqual(self.deployer.current(), self.old)

    def test_stale_plan_refuses_to_publish(self):
        plan = self.make_plan()
        self.deployer.prepare(ID, self.archive(plan))
        other = self.root / "releases" / "other"
        other.mkdir()
        (other / "index.html").write_bytes(b"other")
        self.deployer.switch(other)
        with self.assertRaisesRegex(ValueError, "Current release changed"):
            self.deployer.publish(ID)
        self.assertEqual(self.deployer.current(), other)

    def test_symlink_archive_entry_is_rejected(self):
        plan = self.make_plan()
        path = self.deployer.paths(ID)[1] / "delta.tar.gz"
        with tarfile.open(path, "w:gz") as tar:
            item = tarfile.TarInfo(plan["needed"][0])
            item.type = tarfile.SYMTYPE
            item.linkname = "/etc/passwd"
            tar.addfile(item)
        with self.assertRaisesRegex(ValueError, "unsafe archive entry"):
            self.deployer.prepare(ID, digest(path))

    def test_zero_change_release(self):
        self.after = dict(self.before)
        plan = self.make_plan()
        self.assertEqual(plan["needed"], [])
        self.deployer.prepare(ID, self.archive(plan))
        self.assertTrue(os.path.samefile(self.old / "index.html", self.deployer.paths(ID)[3] / "index.html"))

    def test_modified_base_file_rejected(self):
        plan = self.make_plan()
        checksum = self.archive(plan)
        (self.old / "music/song.mp3").write_bytes(b"unexpected modification")
        with self.assertRaisesRegex(ValueError, "Base file changed"):
            self.deployer.prepare(ID, checksum)
        self.assertEqual(self.deployer.current(), self.old)


if __name__ == "__main__":
    unittest.main(verbosity=2)
