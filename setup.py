"""Build a platform wheel containing the unchanged standalone runtime."""
from pathlib import Path
import platform
import shutil
import sys

from setuptools import Distribution, setup
from setuptools.command.bdist_wheel import bdist_wheel
from setuptools.command.build_py import build_py

sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
from wheel_runtime import obtain_runtime, validate, digest

# Captured third-party responses and cookies used only for offline replay stay out of the wheel.
EXAMPLES_EXCLUDED = shutil.ignore_patterns("__pycache__", "*.pyc", "fixture", "interstitial_fixture",
                                           "replay.py", "interstitial.py", "interstitial_solve.py",
                                           "*_result.json")


class PlatformDistribution(Distribution):
    def has_ext_modules(self):
        return True


class BuildPython(build_py):
    def get_outputs(self, include_bytecode=True):
        outputs = list(super().get_outputs(include_bytecode=include_bytecode))
        examples = Path(self.build_lib) / "ruyijs/examples"
        if examples.exists():
            outputs.extend(str(path) for path in examples.rglob("*") if path.is_file())
        return sorted(set(outputs))

    def run(self):
        linux = sys.platform.startswith("linux")
        if (sys.platform != "win32" and not linux) or platform.machine().lower() not in ("amd64", "x86_64"):
            raise RuntimeError("ruyijs requires Windows or Linux x86_64 and a 64-bit Python installation")
        if sys.maxsize <= 2 ** 32:
            raise RuntimeError("ruyijs requires 64-bit Python")
        super().run()
        target = Path(self.build_lib) / "ruyijs/_runtime"
        if linux:
            project = Path(__file__).resolve().parent
            executable = project / "dist/js"
            if not executable.is_file():
                raise RuntimeError("Build the Linux runtime with tools/build_linux.py before building a wheel")
            with executable.open("rb") as stream:
                header = stream.read(20)
            if header[:6] != b"\x7fELF\x02\x01" or header[18:20] != b"\x3e\x00":
                raise RuntimeError("dist/js is not a native little-endian x86_64 ELF executable")
            from bundle_linux import bundle
            bundle(project, target)
        else:
            runtime = obtain_runtime(Path(__file__).resolve().parent)
            if target.exists():
                validate(target)
                if digest(target / "SHA256SUMS") != digest(runtime / "SHA256SUMS"):
                    raise ValueError(f"Build directory contains another runtime version: {target}")
            else:
                shutil.copytree(runtime, target)
        examples = Path(self.build_lib) / "ruyijs/examples"
        if examples.exists():
            shutil.rmtree(examples)
        shutil.copytree(Path(__file__).resolve().parent / "examples", examples, ignore=EXAMPLES_EXCLUDED)
        registry = Path(__file__).resolve().parent / "python/ruyijs/examples"
        shutil.copytree(registry, examples, dirs_exist_ok=True, ignore=EXAMPLES_EXCLUDED)
        readme = examples / "DataDome/README.md"
        if readme.is_file():
            readme.write_text(
                "> The installed package includes only the live `solve.py` "
                "(`python -m ruyijs.examples datadome`).\n"
                "> Offline replay and device-check scripts and their captured data are not distributed.\n\n"
                + readme.read_text(encoding="utf-8"), encoding="utf-8")


class PlatformWheel(bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False
        self.plat_name = "linux_x86_64" if sys.platform.startswith("linux") else "win_amd64"

    def get_tag(self):
        return "py3", "none", self.plat_name


setup(distclass=PlatformDistribution,
      cmdclass={"build_py": BuildPython, "bdist_wheel": PlatformWheel})
