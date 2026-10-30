"""Build the pinned standalone Necko adapter with native Linux NSS/NSPR."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import venv
import zipfile

DEPENDENCIES = ["requests==2.34.2", "urllib3==2.7.0", "h2==4.4.1",
                "hpack==4.2.0", "hyperframe==6.1.0", "brotli==1.2.0",
                "cryptography==50.0.1", "publicsuffixlist==1.0.2.20260922"]


def run(args, **kwargs):
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firefox-source", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--http3", action="store_true", help="also build Mozilla Neqo's native HTTP/3 bridge")
    args = parser.parse_args()
    if not sys.platform.startswith("linux") or sys.version_info < (3, 14) or args.jobs < 1:
        parser.error("Linux, Python 3.14+ and a positive jobs count are required")
    root = Path(__file__).resolve().parents[1]
    build = root / "build/necko"
    build.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((root / "runtime.json").read_text())
    archive = root / "build/upstream-runtime.zip"
    if not archive.is_file():
        with urllib.request.urlopen(manifest["url"], timeout=120) as source, archive.open("wb") as output:
            shutil.copyfileobj(source, output)
    if (archive.stat().st_size != manifest["size"] or
            hashlib.sha256(archive.read_bytes()).hexdigest() != manifest["sha256"]):
        raise ValueError("Upstream runtime SHA256/size mismatch")
    vendor = root / "vendor/necko-native"
    python_source = vendor / "python"
    inventory = {}
    prefix = "vendor/necko-derived/python/Lib/site-packages/"
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            if not entry.filename.startswith(prefix):
                continue
            relative = Path(entry.filename[len(prefix):])
            if (not relative.parts or relative.parts[0] not in ("necko", "ruyijs_necko") or
                    relative.suffix.lower() not in (".py", ".json", ".pem", ".dat", ".html", ".txt")):
                continue
            content = source.read(entry)
            target = python_source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            # Keep local, reviewed platform edits across subsequent builds.
            if not target.exists():
                target.write_bytes(content)
            inventory[relative.as_posix()] = hashlib.sha256(content).hexdigest()
    (vendor / "upstream.json").write_text(json.dumps({"archive": manifest["url"],
        "sha256": manifest["sha256"], "files": inventory}, indent=2) + "\n")
    runtime = root / "vendor/necko-linux"
    if not (runtime / "bin/pip").exists():
        venv.EnvBuilder(with_pip=True).create(runtime)
    python = runtime / "bin/python3"
    run([python, "-m", "pip", "install", "--disable-pip-version-check", *DEPENDENCIES, "gyp-next==0.21.0"])
    site = subprocess.check_output([python, "-c", "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True).strip()
    Path(site, "ruyijs-necko.pth").write_text(str(python_source) + "\n")
    source = build / "source"
    for origin, name in ((args.firefox_source / "security/nss", "nss"),
                         (args.firefox_source / "nsprpub", "nspr")):
        destination = source / name
        if not destination.exists():
            shutil.copytree(origin, destination, ignore=shutil.ignore_patterns("out", ".git", "obj-*"))
    if args.prepare_only:
        return
    env = dict(os.environ, PATH=str(runtime / "bin") + os.pathsep + os.environ["PATH"])
    run(["bash", "build.sh", "-o", "--clang", "--disable-tests", "-j", args.jobs,
         "--dist=" + str(build / "dist")], cwd=source / "nss", env=env)
    nss = build / "dist/Release"
    target = python_source / "necko"
    for library in (nss / "lib").glob("*.so"):
        shutil.copy2(library, target / library.name)
    run(["clang++", "-std=c++20", "-shared", "-fPIC", "-O2", "-pthread",
         "-I" + str(nss / "include/nspr"), "-I" + str(build / "dist/public/nss"),
         *sorted((vendor / "src").glob("*.cpp")), "-L" + str(target),
         "-Wl,-rpath,$ORIGIN", "-Wl,-z,defs", "-lssl3", "-lnss3", "-lnssutil3", "-lnspr4",
         "-lbrotlidec", "-o", target / "libnecko_core.so"])
    run([python, "-I", "-B", "-c", "from necko._transport import _load_library; "
         "n=_load_library(); print('NSS', n.necko_tls_nss_version().decode(), "
         "'NSPR', n.necko_tls_nspr_version().decode())"])
    if args.http3:
        run([sys.executable, "-B", root / "tools/build_neqo_linux.py",
             "--firefox-source", args.firefox_source, "--jobs", min(args.jobs, 2)])
    http3 = (target / "libnecko_quic.so").is_file()
    (runtime / "backend.json").write_text(json.dumps({"backend": "standalone-necko+nss",
        "nss": "3.131", "http": ["http/1.1", "h2"] + (["h3"] if http3 else []), "http3": http3,
        "python": sys.version.split()[0]}, indent=2) + "\n")


if __name__ == "__main__":
    main()
