"""Build the standalone Neqo HTTP/3 bridge against Firefox's vendored sources."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib


def prepare(root, firefox):
    build = root / "build/necko-quic"
    crates = build / "crates"
    crates.mkdir(parents=True, exist_ok=True)
    inventory = {}
    for name in ("neqo-common", "neqo-http3", "neqo-qpack", "neqo-transport", "nss-rs", "mtu"):
        source = firefox / "third_party/rust" / name
        target = crates / name
        if not target.exists():
            shutil.copytree(source, target)
        for path in source.rglob("*"):
            if path.is_file():
                inventory[f"{name}/{path.relative_to(source).as_posix()}"] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest = (source / "Cargo.toml").read_text()
        manifest = manifest.replace('git = "https://github.com/mozilla/nss-rs"', 'path = "../nss-rs"')
        # These copies build Linux standalone only; Cargo otherwise resolves
        # Windows/macOS and Gecko-only dependencies absent from the donor vendor.
        blocks = re.split(r'(?m)(?=^\[)', manifest)
        manifest = ''.join(b for b in blocks if not (
            b.startswith('[target.') and ('cfg(windows)' in b.splitlines()[0] or
                'target_os = "macos"' in b.splitlines()[0]) or
            b.startswith('[build-dependencies.mozbuild]')))
        manifest = manifest.replace('gecko = ["mozbuild"]', 'gecko = []')
        (target / "Cargo.toml").write_text(manifest)
    # Narrow embedding ports: expose the owned NSS descriptor before starting
    # the handshake so the standalone adapter can apply its TLS profile.
    agent = crates / "nss-rs/src/agent.rs"
    text = (firefox / "third_party/rust/nss-rs/src/agent.rs").read_text()
    text = text.replace('impl SecretAgent {', 'impl SecretAgent {\n'
        '    pub fn standalone_fd(&mut self) -> *mut std::ffi::c_void { self.fd.cast() }', 1)
    agent.write_text(text)
    connection = crates / "neqo-transport/src/connection/mod.rs"
    text = (firefox / "third_party/rust/neqo-transport/src/connection/mod.rs").read_text()
    text = text.replace('    pub fn set_certificate_compression<',
        '    pub fn standalone_tls_fd(&mut self) -> *mut std::ffi::c_void {\n'
        '        self.crypto.tls_mut().standalone_fd()\n    }\n\n'
        '    pub fn set_certificate_compression<', 1)
    connection.write_text(text)
    source = root / "vendor/necko-native/quic"
    # Reuse Firefox's compatibility crates when its vendor inventory has moved
    # ahead of a transitive requirement (bindgen, toml, Windows-only crates).
    patches = tomllib.loads((firefox / "Cargo.toml").read_text())["patch"]["crates-io"]
    patch_lines = []
    for name, values in patches.items():
        if "path" not in values or name not in ("bindgen", "toml_0_9", "windows-targets"):
            continue
        fields = {k: v for k, v in values.items() if k in ("path", "package", "version")}
        fields["path"] = str(firefox / fields["path"])
        patch_lines.append(json.dumps(name) + '={' + ','.join(k + '=' + json.dumps(v) for k, v in fields.items()) + '}\n')
    manifest = ('[package]\nname="necko_quic"\nversion="0.1.0"\nedition="2024"\n'
        '[lib]\ncrate-type=["cdylib"]\npath=' + json.dumps(str(source / "lib.rs")) + '\n'
        '[dependencies]\nserde_json="1"\nbase64="0.22"\nlibc="0.2"\n'
        'neqo-http3={path="crates/neqo-http3",default-features=false}\n'
        'neqo-transport={path="crates/neqo-transport",default-features=false}\n'
        'neqo-common={path="crates/neqo-common",default-features=false}\n'
        'nss={package="nss-rs",path="crates/nss-rs",default-features=false}\n'
        '[patch.crates-io]\n' + ''.join(patch_lines) +
        '[profile.release]\nopt-level=2\ncodegen-units=1\n')
    (build / "Cargo.toml").write_text(manifest)
    lock = source / "Cargo.lock"
    if lock.is_file():
        shutil.copy2(lock, build / "Cargo.lock")
    config = build / ".cargo/config.toml"
    config.parent.mkdir(exist_ok=True)
    config.write_text('[source.crates-io]\nreplace-with="firefox"\n[source.firefox]\ndirectory=' +
        json.dumps(str(firefox / "third_party/rust")) + '\n')
    records = root / "vendor/necko-native/neqo-upstream.json"
    records.write_text(json.dumps({"firefox": "159.0", "neqo": "0.32.0", "nss-rs": "0.16.1",
        "sha256": inventory}, indent=2) + '\n')
    sdk = root / "build/necko/source/dist"
    if not sdk.exists():
        sdk.symlink_to(root / "build/necko/dist", target_is_directory=True)
    return build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firefox-source", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    build = prepare(root, args.firefox_source.resolve())
    if args.prepare_only:
        return
    env = dict(os.environ, NSS_DIR=str(root / "build/necko/source/nss"), NSS_PREBUILT="1",
               RUSTFLAGS="-C link-arg=-Wl,-rpath,$ORIGIN")
    command = ["cargo", "build", "--release", "--offline", "-j", str(args.jobs)]
    if (root / "vendor/necko-native/quic/Cargo.lock").is_file():
        command.append("--locked")
    subprocess.run(command,
        cwd=build, env=env, check=True)
    target = root / "vendor/necko-native/python/necko/libnecko_quic.so"
    shutil.copy2(build / "target/release/libnecko_quic.so", target)
    shutil.copy2(build / "Cargo.lock", root / "vendor/necko-native/quic/Cargo.lock")
    print(target)


if __name__ == "__main__":
    main()
