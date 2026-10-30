"""Read a configured standalone SpiderMonkey build without invoking make."""

import json
import re
import shlex
from pathlib import Path


class Donor:
    def __init__(self, objdir):
        self.obj = Path(objdir).resolve()
        self.config_path = self.obj / "config.status.json"
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.substs = self.config["substs"]
        self.src = Path(self.config["topsrcdir"]).resolve()
        self.shell = self.obj / "js/src/shell"
        self.backend_path = self.shell / "backend.mk"
        self.backend = self.backend_path.read_text(encoding="utf-8")
        required = {"JS_STANDALONE": "1"}
        for name, expected in required.items():
            if str(self.substs.get(name)) != expected:
                raise ValueError(f"donor requires {name}={expected}")
        self.windows = self.substs.get("OS_ARCH") == "WINNT"
        if self.substs.get("OS_ARCH") not in ("WINNT", "Linux"):
            raise ValueError("donor must target Windows or Linux")
        if "x86_64" not in str(self.substs.get("target", "")):
            raise ValueError("donor must target x86_64")
        if self.windows and "-MD" not in self.flags("COMPUTED_CXXFLAGS"):
            raise ValueError("donor must use the shared MSVC CRT (-MD)")

    def values(self, variable):
        pattern = rf"^{re.escape(variable)}\s*(?:\+=|:=|=)\s*(.*)$"
        return re.findall(pattern, self.backend, re.MULTILINE)

    def flags(self, variable):
        # shlex is slow and the donor configuration is fixed for the process.
        cache = self.__dict__.setdefault("_flags", {})
        if variable not in cache:
            cache[variable] = shlex.split(" ".join(self.values(variable)))
        return list(cache[variable])

    def expand(self, text):
        for variable, value in (("DEPTH", self.obj), ("topobjdir", self.obj),
                                ("topsrcdir", self.src)):
            text = text.replace(f"$({variable})", value.as_posix())
        if "$(" in text:
            raise ValueError(f"unresolved make variable: {text}")
        return text

    def libraries(self):
        return [Path(self.expand(item)).resolve()
                for key in ("STATIC_LIBS", "SHARED_LIBS")
                for item in self.flags(key)]

    def objects(self):
        text = (self.shell / ("js_exe.list" if self.windows else "js.list")).read_text(encoding="utf-8")
        return [(self.shell / line.strip().strip('"')).resolve()
                for line in text.splitlines() if line.strip()]

    def libpaths(self, vs_root=None):
        if not self.windows:
            return []
        result = []
        for value in self.substs["HOST_LINKER_LIBPATHS"]:
            path = value.split(":", 1)[1].strip("'\"")
            result.append("-LIBPATH:" + self.remap_vs(path, vs_root))
        return result

    def include(self, vs_root=None):
        return ";".join(self.remap_vs(path, vs_root)
                        for path in self.substs["INCLUDE"].split(";"))

    @staticmethod
    def remap_vs(path, vs_root):
        marker = "/.mozbuild/vs/"
        if vs_root is None:
            return path
        normalized = path.replace("\\", "/")
        if marker not in normalized:
            raise ValueError(f"unexpected VS path: {path}")
        return (Path(vs_root) / normalized.split(marker, 1)[1]).as_posix()

    def source_inputs(self):
        return [self.config_path, self.backend_path, self.shell / ("js_exe.list" if self.windows else "js.list"),
                self.shell / "Unified_cpp_js_src_shell0.cpp",
                self.obj / "js/src/js-confdefs.h", self.src / "js/src/shell/js.cpp"]
