"""Collect comparable text metrics, Canvas RGBA and PNG from Windows or Linux."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context

METRICS = ("width actualBoundingBoxLeft actualBoundingBoxRight actualBoundingBoxAscent "
           "actualBoundingBoxDescent fontBoundingBoxAscent fontBoundingBoxDescent "
           "emHeightAscent emHeightDescent hangingBaseline alphabeticBaseline ideographicBaseline").split()
CASES = [("latin", "16px Arial", "AVATAR office ffi Wj"),
         ("fractional", "17.3px Arial", "AV AV AV AV"),
         ("italic", "italic 27px Times New Roman", "fjy AV fi"),
         ("marks", "24px Arial", "e\u0301 \u00e9 a\u0308 \u00e4"),
         ("cjk", "20px Microsoft YaHei", "\u5b57\u4f53\u5ea6\u91cf Canvas"),
         ("emoji", "24px Segoe UI Emoji", "\U0001f600\U0001f469\u200d\U0001f4bb"),
         ("rtl", "24px Arial", "\u0645\u0631\u062d\u0628\u0627"),
         ("empty", "16px Arial", "")]


def png_content_hash(png):
    # Preserve the raw hash too: deBG is the upstream session-random metadata,
    # and a different session key is independent of glyph/pixel alignment.
    normalized = png[:8]
    offset = 8
    while offset < len(png):
        size = int.from_bytes(png[offset:offset + 4], "big") + 12
        if size < 12 or offset + size > len(png):
            raise ValueError("Truncated PNG chunk")
        if png[offset + 4:offset + 8] != b"deBG":
            normalized += png[offset:offset + size]
        offset += size
    return hashlib.sha256(normalized).hexdigest()


def capture(font_directory=None):
    if font_directory:
        os.environ["RUYIJS_FONT_DIRECTORY"] = str(font_directory.resolve())
    report = {"schema": 1, "platform": sys.platform, "fontFiles": {}, "cases": {}}
    if font_directory:
        for p in sorted(font_directory.rglob("*")):
            if p.suffix.lower() in (".ttf", ".ttc", ".otf"):
                report["fontFiles"][p.relative_to(font_directory).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    with Context(timeout=30) as ctx:
        ctx.load_page("https://rendering.test/", "<!doctype html><html><body></body></html>")
        for name, font, text in CASES:
            ctx.set("probeInput", {"font": font, "text": text, "metrics": METRICS})
            case = ctx.eval("""(() => {
              const c=document.createElement('canvas');c.width=320;c.height=80;
              const g=c.getContext('2d');g.font=probeInput.font;
              const m=g.measureText(probeInput.text), metrics={};
              for(const k of probeInput.metrics) metrics[k]=m[k];
              g.fillStyle='#fff';g.fillRect(0,0,320,80);g.fillStyle='#174d93';
              g.fillText(probeInput.text,8.25,45.5);
              const span=document.createElement('span');span.style.font=probeInput.font;
              span.textContent=probeInput.text;document.body.appendChild(span);
              const r=span.getBoundingClientRect();
              const pixels=g.getImageData(0,0,320,80).data;let raw='';
              for(let i=0;i<pixels.length;i+=8192)raw+=String.fromCharCode(...pixels.subarray(i,i+8192));
              const result={font:g.font,text:probeInput.text,metrics,rect:[r.x,r.y,r.width,r.height],
                rgba:btoa(raw),png:c.toDataURL()};
              span.remove();return result;
            })()""")
            pixels = base64.b64decode(case.pop("rgba"))
            png = base64.b64decode(case.pop("png").partition(",")[2])
            case.update(rgba=base64.b64encode(pixels).decode(),
                rgbaSha256=hashlib.sha256(pixels).hexdigest(), pngSha256=hashlib.sha256(png).hexdigest(),
                pngWithoutSessionMetadataSha256=png_content_hash(png))
            report["cases"][name] = case
    return report


def compare(actual, expected):
    differences = {}
    for name, case in actual["cases"].items():
        other = expected["cases"].get(name)
        if other is None:
            differences[name] = {"missingBaseline": True}
            continue
        a, b = base64.b64decode(case["rgba"]), base64.b64decode(other["rgba"])
        pairs = list(zip(a, b))
        differences[name] = {"metrics": {key: {"actual": case["metrics"][key], "expected": other["metrics"][key]}
            for key in METRICS if case["metrics"][key] != other["metrics"][key]},
            "rgbaEqual": a == b, "changedChannels": sum(x != y for x, y in pairs) + abs(len(a) - len(b)),
            "maxChannelDifference": max((abs(x - y) for x, y in pairs), default=0),
            "pngEqual": case["pngSha256"] == other["pngSha256"],
            "pngContentEqual": case.get("pngWithoutSessionMetadataSha256") == other.get("pngWithoutSessionMetadataSha256"),
            "rectEqual": case["rect"] == other["rect"]}
    inventory = actual["fontFiles"] == expected["fontFiles"] if actual["fontFiles"] and expected["fontFiles"] else None
    return {"fontFilesEqual": inventory, "cases": differences}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--font-directory", type=Path)
    args = parser.parse_args()
    if args.font_directory and not args.font_directory.is_dir():
        parser.error("font directory does not exist")
    report = capture(args.font_directory)
    if args.baseline:
        report["comparison"] = compare(report, json.loads(args.baseline.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=True, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "cases": len(report["cases"]),
        "comparison": report.get("comparison")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
