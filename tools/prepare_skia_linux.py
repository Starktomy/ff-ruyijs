"""Prepare Firefox 159's Skia 149 raster sources for a standalone Linux build.

The donor is read only. Retain Mozilla's color/gamma/raster configuration and
source-specific SIMD flags; replace its Gecko allocator and Cairo font port
with Skia's standalone malloc/Fontconfig/FreeType ports.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from provenance import write_if_changed
from types import SimpleNamespace


class Sources(list):
    def __init__(self):
        super().__init__()
        self.options = defaultdict(lambda: SimpleNamespace(flags=[]))

    def __getitem__(self, key):
        return self.options[key] if isinstance(key, str) else super().__getitem__(key)


def fontconfig_source(source, output):
    """Use Fontconfig's binding query instead of Skia's pre-2.12.5 probe.

    The donor's old probe allocates patterns, language sets and a font set and
    runs a dummy font match for every family substitution. Modern Fontconfig
    exposes the same weak/strong bit directly. Keep the donor fallback for old
    headers and write only the derived build source, never the donor tree.
    """
    text = source.read_text()
    start = "static SkWeakReturn is_weak(FcPattern* pattern, const char object[], int id) {\n"
    end = "\n/** Removes weak elements from either FC_FAMILY or FC_POSTSCRIPT_NAME objects in the property."
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("Donor Skia Fontconfig binding probe changed")
    first = text.index(start) + len(start)
    last = text.index(end, first)
    fallback = text[first:last]
    if not fallback.endswith("}\n"):
        raise ValueError("Donor Skia Fontconfig binding probe end changed")
    direct = """#if FC_VERSION >= 21205
    FCLocker::AssertHeld();
    FcValue value;
    FcValueBinding binding;
    if (FcPatternGetWithBinding(pattern, object, id, &value, &binding) != FcResultMatch) {
        return kNoId_WeakReturn;
    }
    return binding == FcValueBindingWeak ? kIsWeak_WeakReturn : kIsStrong_WeakReturn;
#else
"""
    text = text[:first] + direct + fallback[:-2] + "#endif\n}\n" + text[last:]
    write_if_changed(output, text)
    return output


def prepare(firefox, output):
    directory = firefox / 'gfx/skia'
    sources, unified = Sources(), Sources()
    config = defaultdict(bool, MOZ_OPTIMIZE=True, CC_TYPE='clang',
                         MOZ_WIDGET_TOOLKIT='gtk', INTEL_ARCHITECTURE=True, TARGET_CPU='x86_64',
                         CAIRO_FT_CFLAGS=[], MOZ_PANGO_CFLAGS=[])
    scope = dict(CONFIG=config, SOURCES=sources, UNIFIED_SOURCES=unified,
                 DEFINES={}, LOCAL_INCLUDES=[], CXXFLAGS=[], LICENSES=Sources(), LICENSED_UNDER=[],
                 AllowCompilerWarnings=lambda: None)
    exec(compile((directory / 'moz.build').read_text(), str(directory / 'moz.build'), 'exec'), scope)
    files = set(sources + unified)
    files -= {'skia/src/ports/SkMemory_mozalloc.cpp', 'skia/src/ports/SkFontHost_cairo.cpp'}
    files.update('skia/src/ports/' + name + '.cpp' for name in
                 ('SkMemory_malloc', 'SkFontMgr_fontconfig', 'SkFontHost_FreeType', 'SkTypeface_proxy'))
    fontconfig = 'skia/src/ports/SkFontMgr_fontconfig.cpp'
    derived = fontconfig_source(directory / fontconfig,
                                output.parent / 'SkFontMgr_fontconfig.cpp')
    lines = ['add_library(firefox_skia STATIC']
    lines.extend('  ' + json.dumps(str(derived if name == fontconfig else directory / name))
                 for name in sorted(files))
    lines += [')', 'set_target_properties(firefox_skia PROPERTIES POSITION_INDEPENDENT_CODE ON)',
              'target_compile_features(firefox_skia PUBLIC cxx_std_20)',
              'target_include_directories(firefox_skia PUBLIC ' + json.dumps(str(directory / 'skia')) + ')',
              'target_link_libraries(firefox_skia PUBLIC PkgConfig::SKIA_DEPS)',
              'target_compile_options(firefox_skia PRIVATE -O2 -fno-rtti -fno-exceptions -ffp-contract=off -Wno-deprecated-declarations)',
              'target_compile_definitions(firefox_skia PRIVATE NDEBUG SKIA_IMPLEMENTATION SK_PDF_USE_HARFBUZZ_SUBSET=1)']
    for name, opts in sorted(sources.options.items()):
        if name not in files or not opts.flags:
            continue
        lines += ['set_source_files_properties(' + json.dumps(str(directory / name)) +
                  ' PROPERTIES COMPILE_OPTIONS ' + json.dumps(';'.join(opts.flags)) + ')']
    write_if_changed(output, '\n'.join(lines) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firefox-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.firefox_source.resolve(), args.output)
