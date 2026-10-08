#!/usr/bin/env python3
"""Immutable Hugo releases: checksum delta uploads, hard links, health checks."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tarfile
import urllib.request
import uuid


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("Invalid relative file path")
    p = PurePosixPath(value)
    if p.is_absolute() or str(p) != value or any(x in (".", "..") for x in p.parts):
        raise ValueError("Unsafe file path: " + value)
    if any(ord(c) < 32 for c in value):
        raise ValueError("Control character in file path")
    return value


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with open(temp, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


class Deployer:
    def __init__(self, root, base_url="https://hitszjla.club/"):
        self.root = Path(root).resolve()
        if self.root == Path("/"):
            raise ValueError("The filesystem root cannot be a deployment root")
        self.releases = self.root / "releases"
        self.control = self.root / ".deploy"
        self.base_url = base_url.rstrip("/")

    @contextlib.contextmanager
    def locked(self):
        self.root.mkdir(parents=True, exist_ok=True)
        # Same lock as the earlier manual deployment procedure.
        with open(self.root / ".deploy.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield

    def paths(self, release_id):
        if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[0-9]{3}-[0-9a-f]{7,40}", release_id):
            raise ValueError("Invalid release ID")
        return (self.control / "state" / release_id,
                self.control / "incoming" / release_id,
                self.control / "staging" / release_id,
                self.releases / release_id)

    def current(self):
        pointer = self.root / "current"
        if not pointer.is_symlink():
            raise ValueError("current must be a symlink")
        target = pointer.resolve(strict=True)
        if target.parent != self.releases.resolve() or not target.is_dir():
            raise ValueError("current points outside the releases directory")
        return target

    def state(self, release_id):
        state_dir, _, _, _ = self.paths(release_id)
        return json.loads((state_dir / "state.json").read_text(encoding="utf-8"))

    def write_state(self, release_id, state):
        save_json(self.paths(release_id)[0] / "state.json", state)

    def status(self, release_id=None):
        result = {"current": str(self.current())}
        if release_id:
            result["release"] = self.state(release_id)
        return result

    def begin(self, release_id):
        state_dir, incoming, stage, release = self.paths(release_id)
        if any(p.exists() or p.is_symlink() for p in (state_dir, incoming, stage, release)):
            raise ValueError("Release ID already exists; start a new deployment")
        self.current()
        incoming.mkdir(parents=True, mode=0o700)
        self.write_state(release_id, {"id": release_id, "phase": "awaiting_manifest"})
        return {"incoming": str(incoming)}

    def manifest(self, path):
        if path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("Manifest too large")
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if data.get("schema") != 1 or not re.fullmatch(r"[0-9a-f]{40}", data.get("commit", "")):
            raise ValueError("Invalid manifest schema or commit")
        files = data.get("files")
        if not isinstance(files, dict) or not files or len(files) > 100000:
            raise ValueError("Invalid file list")
        for name, info in files.items():
            relative_path(name)
            if not isinstance(info, dict) or not re.fullmatch(r"[0-9a-f]{64}", info.get("sha256", "")):
                raise ValueError("Invalid checksum: " + name)
            if type(info.get("size")) is not int or info["size"] < 0:
                raise ValueError("Invalid size: " + name)
            if any(str(parent) in files for parent in PurePosixPath(name).parents if str(parent) != "."):
                raise ValueError("Conflicting file/directory paths")
        for required in ("index.html", "index.json", "events/index.html", "news/index.html"):
            if required not in files or not files[required]["size"]:
                raise ValueError("Missing required file: " + required)
        checks = data.get("check_files", [])
        if not isinstance(checks, list):
            raise ValueError("Invalid check_files")
        for name in checks:
            relative_path(name)
            if name not in files or not name.endswith((".html", ".json")):
                raise ValueError("Health check must name a generated HTML or JSON file")
        return data

    def plain_file(self, base, name):
        p = base
        for part in PurePosixPath(name).parts:
            p = p / part
            if p.is_symlink():
                return False
        return p.is_file()

    def matches(self, base, name, info):
        p = base / name
        return (self.plain_file(base, name) and p.stat().st_size == info["size"]
                and digest(p) == info["sha256"])

    def plan(self, release_id):
        state_dir, incoming, _, _ = self.paths(release_id)
        state = self.state(release_id)
        if state["phase"] != "awaiting_manifest":
            raise ValueError("Release is not awaiting its manifest")
        manifest = self.manifest(incoming / "manifest.json")
        old = self.current()
        needed = [name for name, info in manifest["files"].items()
                  if not self.matches(old, name, info)]
        checks = list(dict.fromkeys(["index.html"] + manifest.get("check_files", [])))
        if len(checks) == 1:
            article = next((name for name in needed if re.fullmatch(r"(?:events|news)/[^/]+/index.html", name)), None)
            if article:
                checks.append(article)
        state.update(phase="planned", base=str(old), commit=manifest["commit"],
                     needed=needed, checks=checks,
                     new_bytes=sum(manifest["files"][n]["size"] for n in needed),
                     reused_files=len(manifest["files"]) - len(needed))
        save_json(state_dir / "manifest.json", manifest)
        self.write_state(release_id, state)
        return state

    def clean_directory(self, path, parent):
        # Only private, per-release staging/incoming directories may be removed.
        if path.parent != parent or path.is_symlink():
            raise ValueError("Unsafe cleanup path")
        if path.exists():
            if path.resolve().parent != parent.resolve():
                raise ValueError("Cleanup path escaped its parent")
            shutil.rmtree(path)

    def cleanup(self, release_id):
        _, incoming, stage, _ = self.paths(release_id)
        self.clean_directory(incoming, self.control / "incoming")
        self.clean_directory(stage, self.control / "staging")
        return {"cleaned": release_id, "releases_preserved": True}

    def verify_release(self, release_id):
        state_dir, _, _, release = self.paths(release_id)
        manifest = self.manifest(state_dir / "manifest.json")
        actual = {p.relative_to(release).as_posix() for p in release.rglob("*") if p.is_file() or p.is_symlink()}
        if actual != set(manifest["files"]):
            raise ValueError("Release file list differs from manifest")
        for name, info in manifest["files"].items():
            if not self.matches(release, name, info):
                raise ValueError("Release checksum mismatch: " + name)
        return manifest

    def prepare(self, release_id, archive_sha):
        state_dir, incoming, stage, release = self.paths(release_id)
        state = self.state(release_id)
        if state["phase"] != "planned":
            raise ValueError("Release is not in planned state")
        old = self.current()
        if str(old) != state["base"]:
            raise ValueError("Current release changed; start a new deployment")
        if stage.exists() or stage.is_symlink() or release.exists() or release.is_symlink():
            raise ValueError("Target exists; clean failed staging or start a new deployment")
        archive = incoming / "delta.tar.gz"
        if not re.fullmatch(r"[0-9a-f]{64}", archive_sha) or digest(archive) != archive_sha:
            raise ValueError("Uploaded archive checksum mismatch")
        manifest = self.manifest(state_dir / "manifest.json")
        needed = set(state["needed"])
        stage.mkdir(parents=True, mode=0o755)
        try:
            seen = set()
            with tarfile.open(archive, "r|gz") as tar:
                for entry in tar:
                    name = relative_path(entry.name)
                    if not entry.isfile() or name not in needed or name in seen:
                        raise ValueError("Unexpected or unsafe archive entry: " + name)
                    info = manifest["files"][name]
                    if entry.size != info["size"]:
                        raise ValueError("Archive size mismatch: " + name)
                    destination = stage / name
                    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                    with tar.extractfile(entry) as source, open(destination, "xb") as output:
                        shutil.copyfileobj(source, output)
                    destination.chmod(0o644)
                    if not self.matches(stage, name, info):
                        raise ValueError("Archive content mismatch: " + name)
                    seen.add(name)
            if seen != needed:
                raise ValueError("Archive is missing required files")
            for name, info in manifest["files"].items():
                if name in needed:
                    continue
                if not self.matches(old, name, info):
                    raise ValueError("Base file changed since planning: " + name)
                destination = stage / name
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                os.link(old / name, destination)
            self.releases.mkdir(parents=True, exist_ok=True)
            os.rename(stage, release)
        except Exception:
            self.clean_directory(stage, self.control / "staging")
            raise
        self.verify_release(release_id)
        state.update(phase="prepared", total_files=len(manifest["files"]))
        self.write_state(release_id, state)
        self.cleanup(release_id)
        return state

    def switch(self, target):
        target = Path(target).resolve(strict=True)
        if target.parent != self.releases.resolve() or not (target / "index.html").is_file():
            raise ValueError("Invalid release target")
        temp = self.root / (".current-" + uuid.uuid4().hex)
        try:
            temp.symlink_to(target, target_is_directory=True)
            os.replace(temp, self.root / "current")
        finally:
            if temp.is_symlink():
                temp.unlink()

    def health(self, release, checks):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for name in checks:
            path = "" if name == "index.html" else (name[:-10] if name.endswith("index.html") else name)
            url = self.base_url + "/" + urllib.request.quote(path, safe="/") + "?deploy_check=" + uuid.uuid4().hex
            request = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "Accept-Encoding": "identity"})
            with opener.open(request, timeout=20) as response:
                if response.status != 200:
                    raise ValueError("Health check failed: " + url)
                actual = hashlib.sha256(response.read()).hexdigest()
            if actual != digest(release / name):
                raise ValueError("Live page does not match the release: " + name)

    def publish(self, release_id):
        _, _, _, release = self.paths(release_id)
        state = self.state(release_id)
        if state["phase"] != "prepared":
            raise ValueError("Release is not prepared")
        old = self.current()
        if str(old) != state["base"]:
            raise ValueError("Current release changed; start a new deployment")
        self.verify_release(release_id)
        state.update(phase="activating", previous=str(old))
        self.write_state(release_id, state)
        self.switch(release)
        try:
            self.health(release, state["checks"])
        except Exception as exc:
            self.switch(old)
            state.update(phase="rolled_back", health_error=str(exc))
            self.write_state(release_id, state)
            raise ValueError("Health check failed; previous release restored: " + str(exc)) from exc
        state.update(phase="published")
        self.write_state(release_id, state)
        return {"id": release_id, "phase": "published", "current": str(release),
                "previous": str(old), "new_bytes": state["new_bytes"],
                "reused_files": state["reused_files"], "checks": state["checks"]}

    def rollback(self, release_id):
        _, _, _, release = self.paths(release_id)
        state = self.state(release_id)
        if self.current() != release or "previous" not in state:
            raise ValueError("This release is not current or has no rollback record")
        previous = Path(state["previous"])
        self.switch(previous)
        state.update(phase="rolled_back")
        self.write_state(release_id, state)
        self.health(previous, ["index.html"])
        return {"phase": "rolled_back", "current": str(previous)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/var/www/HITsz-JLA-web")
    parser.add_argument("--base-url", default="https://hitszjla.club/")
    parser.add_argument("action", choices=["status", "begin", "plan", "prepare", "publish", "rollback", "cleanup"])
    parser.add_argument("release_id", nargs="?")
    parser.add_argument("--sha256")
    args = parser.parse_args()
    deployer = Deployer(args.root, args.base_url)
    if args.action != "status" and not args.release_id:
        parser.error("release_id is required")
    with deployer.locked():
        if args.action == "status":
            result = deployer.status(args.release_id)
        elif args.action == "prepare":
            result = deployer.prepare(args.release_id, args.sha256 or "")
        else:
            result = getattr(deployer, args.action)(args.release_id)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
