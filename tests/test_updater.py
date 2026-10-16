import hashlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from closeall import __version__, cli, settings, updater

EXE = b"MZ" + b"\x90" * 5000
URL = updater.DOWNLOAD_PREFIX + "v9.0.0/"


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def release_json(tag="v9.0.0", payload=EXE, digest=True, assets=(updater.GUI_ASSET, updater.CLI_ASSET)):
    sha = hashlib.sha256(payload).hexdigest()
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/{updater.REPOSITORY}/releases/tag/{tag}",
        "assets": [{"name": name, "browser_download_url": URL + name, "size": len(payload),
                    "digest": f"sha256:{sha}" if digest else None} for name in assets],
    }


class Opener:
    """Fake urlopen: the API answer, then the executable bytes."""

    def __init__(self, release=None, payload=EXE, error=None):
        self.release, self.payload, self.error = release or release_json(), payload, error
        self.urls = []

    def __call__(self, request, timeout):
        self.urls.append(request.full_url)
        if self.error:
            raise self.error
        if request.full_url == updater.LATEST_API:
            return Response(json.dumps(self.release).encode())
        return Response(self.payload)


class VersionTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(updater.parse_version("v1.6.0"), (1, 6, 0))
        self.assertEqual(updater.parse_version("1.6"), (1, 6))
        self.assertIsNone(updater.parse_version("v1.6.0-beta"))
        self.assertIsNone(updater.parse_version(""))

    def test_newer(self):
        release = updater.Release("v1.5.1", (1, 5, 1), "")
        self.assertFalse(updater.is_newer(release, "1.5.1"))
        self.assertTrue(updater.is_newer(release, "1.5"))
        self.assertTrue(updater.is_newer(updater.Release("v1.10", (1, 10), ""), "1.9.9"))
        self.assertFalse(updater.is_newer(updater.Release("v1.5", (1, 5), ""), "1.5.0"))


class FetchTests(unittest.TestCase):
    def test_latest_release(self):
        release = updater.fetch_latest(Opener())
        self.assertEqual(release.label, "9.0.0")
        asset = release.assets[updater.GUI_ASSET.lower()]
        self.assertEqual(asset.sha256, hashlib.sha256(EXE).hexdigest())

    def test_network_error(self):
        with self.assertRaises(updater.UpdateError) as ctx:
            updater.fetch_latest(Opener(error=urllib.error.URLError("offline")))
        self.assertEqual(ctx.exception.key, "update_err_network")

    def test_bad_answer(self):
        with self.assertRaises(updater.UpdateError) as ctx:
            updater.fetch_latest(Opener(release={"message": "rate limited"}))
        self.assertEqual(ctx.exception.key, "update_err_response")

    def test_asset_choice(self):
        release = updater.fetch_latest(Opener())
        self.assertEqual(updater.asset_for(release, r"C:\Tools\closeallpython.exe").name, updater.GUI_ASSET)
        self.assertEqual(updater.asset_for(release, r"C:\Tools\CloseAll-cli.exe").name, updater.CLI_ASSET)
        self.assertEqual(updater.asset_for(release, r"C:\Tools\renamed.exe").name, updater.GUI_ASSET)

    def test_asset_without_checksum_is_refused(self):
        release = updater.fetch_latest(Opener(release_json(digest=False)))
        with self.assertRaises(updater.UpdateError) as ctx:
            updater.asset_for(release, "CloseAllPython.exe")
        self.assertEqual(ctx.exception.key, "update_err_unverifiable")

    def test_missing_asset(self):
        release = updater.fetch_latest(Opener(release_json(assets=(updater.CLI_ASSET,))))
        with self.assertRaises(updater.UpdateError) as ctx:
            updater.asset_for(release, "CloseAllPython.exe")
        self.assertEqual(ctx.exception.key, "update_err_no_asset")

    def test_foreign_download_url_is_refused(self):
        data = release_json()
        data["assets"][0]["browser_download_url"] = "https://example.com/CloseAllPython.exe"
        release = updater.fetch_latest(Opener(data))
        with self.assertRaises(updater.UpdateError):
            updater.asset_for(release, "CloseAllPython.exe")


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.exe = self.dir / "CloseAllPython.exe"
        self.exe.write_bytes(b"MZ old version")

    def tearDown(self):
        for path in self.dir.iterdir():
            path.unlink()
        self.dir.rmdir()

    def names(self):
        return sorted(p.name for p in self.dir.iterdir())

    def test_update_replaces_the_executable(self):
        release = updater.fetch_latest(Opener())
        seen = []
        updater.update(self.exe, release, Opener(), progress=lambda done, total: seen.append((done, total)))
        self.assertEqual(self.exe.read_bytes(), EXE)
        self.assertEqual(self.names(), ["CloseAllPython.exe", "CloseAllPython.exe.old"])
        self.assertEqual(seen[-1], (len(EXE), len(EXE)))
        updater.cleanup(self.exe)
        self.assertEqual(self.names(), ["CloseAllPython.exe"])

    def test_corrupted_download_changes_nothing(self):
        release = updater.fetch_latest(Opener())
        tampered = b"MZ" + b"\x00" * (len(EXE) - 2)
        with self.assertRaises(updater.UpdateError) as ctx:
            updater.update(self.exe, release, Opener(payload=tampered))
        self.assertEqual(ctx.exception.key, "update_err_verify")
        self.assertEqual(self.exe.read_bytes(), b"MZ old version")
        self.assertEqual(self.names(), ["CloseAllPython.exe"])

    def test_wrong_size_or_not_an_executable(self):
        release = updater.fetch_latest(Opener())
        for payload in (EXE[:-10], EXE + b"x", b"PK" + EXE[2:]):
            with self.assertRaises(updater.UpdateError):
                updater.update(self.exe, release, Opener(payload=payload))
            self.assertEqual(self.names(), ["CloseAllPython.exe"])

    def test_failed_swap_restores_the_old_version(self):
        new = self.dir / "CloseAllPython.exe.new"
        new.write_bytes(EXE)
        real_replace = os.replace

        def replace(src, dst):
            if Path(src) == new:
                raise PermissionError(13, "Access is denied")
            return real_replace(src, dst)

        with mock.patch.object(updater.os, "replace", replace):
            with self.assertRaises(updater.UpdateError) as ctx:
                updater.install(new, self.exe)
        self.assertEqual(ctx.exception.key, "update_err_write")
        self.assertEqual(self.exe.read_bytes(), b"MZ old version")
        self.assertEqual(self.names(), ["CloseAllPython.exe"])

    def test_old_copy_still_in_use_gets_another_name(self):
        (self.dir / "CloseAllPython.exe.old").write_bytes(b"held")
        real_remove = os.remove

        def remove(path):
            if Path(path).name == "CloseAllPython.exe.old":
                raise PermissionError(13, "in use")
            return real_remove(path)

        new = self.dir / "CloseAllPython.exe.new"
        new.write_bytes(EXE)
        with mock.patch.object(updater.os, "remove", remove):
            updater.install(new, self.exe)
        self.assertIn("CloseAllPython.exe.old2", self.names())
        self.assertEqual(self.exe.read_bytes(), EXE)


class SettingsAndCliTests(unittest.TestCase):
    def test_auto_update_setting(self):
        self.assertFalse(settings.parse_settings({})["auto_update"])
        self.assertTrue(settings.parse_settings({"auto_update": True})["auto_update"])
        self.assertFalse(settings.parse_settings({"auto_update": "true"})["auto_update"])

    def test_update_option_stands_alone(self):
        self.assertTrue(cli.parse_args(["--update"], "en").update)
        with self.assertRaises(SystemExit), mock.patch("sys.stderr", io.StringIO()):
            cli.parse_args(["--update", "--no-ui", "--all"], "en")

    def run_update(self, opener, exe_path=None, frozen=False):
        out, err = io.StringIO(), io.StringIO()
        fake = mock.Mock(wraps=updater)
        fake.UpdateError = updater.UpdateError
        fake.fetch_latest = lambda: updater.fetch_latest(opener)
        fake.update = lambda exe, release: updater.update(exe, release, opener)
        fake.current_executable = lambda: exe_path if frozen else None
        code = cli.run_update({"language": "en"}, out, err, updater=fake)
        return code, out.getvalue(), err.getvalue()

    def test_cli_up_to_date(self):
        code, out, _ = self.run_update(Opener(release_json(tag="v" + __version__)))
        self.assertEqual(code, 0)
        self.assertIn("up to date", out)

    def test_cli_from_source(self):
        code, out, _ = self.run_update(Opener())
        self.assertEqual(code, 0)
        self.assertIn("git pull", out)

    def test_cli_installs(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "CloseAllPython-CLI.exe"
            exe.write_bytes(b"MZ old")
            code, out, err = self.run_update(Opener(), exe, frozen=True)
            self.assertEqual((code, err), (0, ""))
            self.assertIn("9.0.0 installed", out)
            self.assertEqual(exe.read_bytes(), EXE)

    def test_cli_network_failure(self):
        code, _, err = self.run_update(Opener(error=urllib.error.URLError("offline")))
        self.assertEqual(code, 1)
        self.assertIn("GitHub cannot be reached", err)


if __name__ == "__main__":
    unittest.main()
