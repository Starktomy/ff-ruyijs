"""Generated profiles stay reproducible, independent and usable by the engine."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from ruyijs import Context, generate_profile
from ruyijs import profile_generator as generator, turnstile


class ProfileGeneratorTests(unittest.TestCase):
    def test_reproducible_independent_profiles_do_not_change_global_random_state(self):
        state = random.getstate()
        for os_name in ("linux", "windows"):
            original = generate_profile(os_name, seed=42)
            duplicate = generate_profile(os_name, seed=42)
            self.assertEqual(original, duplicate)
            self.assertNotEqual(original, generate_profile(os_name, seed=43))
            duplicate["navigator"]["languages"].clear()
            duplicate["webgl"]["attributes"]["alpha"] = False
            duplicate["webgl"]["extensions"].clear()
            self.assertEqual(original, generate_profile(os_name, seed=42))
        self.assertEqual(random.getstate(), state)

    def test_os_identity_display_bounds_and_locale_are_consistent(self):
        for os_name in ("linux", "windows"):
            profiles = [generate_profile(os_name, seed=seed, locale="ko-KR") for seed in range(50)]
            self.assertGreater(len({json.dumps(p, sort_keys=True) for p in profiles}), 40)
            for profile in profiles:
                nav, screen, viewport = (profile[k] for k in ("navigator", "screen", "viewport"))
                self.assertIn("Firefox/159.0", nav["userAgent"])
                self.assertIn("rv:159.0", nav["userAgent"])
                self.assertEqual(nav["platform"], "Linux x86_64" if os_name == "linux" else "Win32")
                self.assertIn("Linux" if os_name == "linux" else "Windows", nav["oscpu"])
                self.assertIn("llvmpipe" if os_name == "linux" else "Direct3D11", profile["webgl"]["renderer"])
                self.assertEqual(nav["language"], nav["languages"][0])
                self.assertEqual(profile["locale"], {"timezone": "Asia/Seoul", "osLocale": "ko-KR"})
                self.assertLessEqual(viewport["width"], screen["availWidth"])
                self.assertLess(viewport["height"], screen["availHeight"])
                self.assertLessEqual(screen["availHeight"], screen["height"])
                self.assertGreater(viewport["width"], 0)
                self.assertGreater(viewport["height"], 0)
                self.assertEqual(screen["colorDepth"], screen["pixelDepth"])

    def test_explicit_fields_are_respected_and_timezone_defaults_are_portable(self):
        with patch.object(generator, "ZoneInfo", side_effect=AssertionError("no system tzdata")):
            for locale in generator._LOCALES:
                profile = generate_profile("windows", seed=7, locale=locale)
                self.assertEqual(profile["navigator"]["language"], locale)
        profile = generate_profile("windows", seed=7, locale="zh-CN", timezone="UTC",
                                   hardware_concurrency=6, screen_size=(1920, 1080),
                                   device_pixel_ratio=1.25)
        self.assertEqual(profile["navigator"]["hardwareConcurrency"], 6)
        self.assertEqual(profile["locale"], {"timezone": "UTC", "osLocale": "zh-CN"})
        self.assertEqual([profile["screen"][k] for k in ("width", "height")], [1920, 1080])
        self.assertEqual(profile["viewport"]["devicePixelRatio"], 1.25)
        # Screen and viewport use the same CSS units, not a second division by DPR.
        self.assertGreaterEqual(profile["viewport"]["width"], 1760)

    def test_invalid_options_are_rejected(self):
        options = [
            {"os_name": value} for value in ("macos", "", None, [])
        ] + [{"seed": value} for value in (-1, True, "42", 1.2)] + [
            {"locale": value} for value in ("invalid", "", None, [])
        ] + [{"hardware_concurrency": value} for value in (0, 65, True, 2.5, "4")] + [
            {"screen_size": value} for value in ((0, 1080), (1920, 0), (8000, 600),
                                                (800, 5000), (True, 800), (800,), "1920x1080")
        ] + [{"device_pixel_ratio": value} for value in (0, 5, float("nan"), float("inf"),
                                                        True, "1.25", 10 ** 400)] + [
            {"timezone": value} for value in ("", "../UTC", "Mars/Olympus", "\0", "+08:00", 3)
        ]
        for kwargs in options:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                generate_profile(**kwargs)

    def test_cli_single_and_batch_files_match_the_python_api(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            single = root / "nested/profile.json"
            self.assertEqual(generator.main(["--os", "windows", "--seed", "42", "--locale", "zh-CN",
                                             "--output", str(single)]), 0)
            self.assertEqual(json.loads(single.read_text()), generate_profile("windows", seed=42, locale="zh-CN"))
            self.assertEqual(generator.main(["--seed", "10", "--count", "3", "--output-dir", str(root)]), 0)
            for index, seed in enumerate(range(10, 13), 1):
                self.assertEqual(json.loads((root / f"linux-{index:04d}.json").read_text()),
                                 generate_profile("linux", seed=seed))
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(generator.main(["--seed", "10", "--count", "2"]), 0)
            self.assertEqual(json.loads(output.getvalue()), [generate_profile(seed=seed) for seed in (10, 11)])
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                generator.main(["--count", "2", "--output", str(single)])
            self.assertEqual(caught.exception.code, 2)

    def test_module_entry_point_emits_only_json(self):
        process = subprocess.run([sys.executable, "-B", "-m", "ruyijs.profile_generator",
                                  "--os", "windows", "--seed", "23"],
                                 env=dict(os.environ, PYTHONPATH=str(ROOT / "python")),
                                 capture_output=True, text=True, check=True)
        self.assertEqual(process.stderr, "")
        self.assertEqual(json.loads(process.stdout), generate_profile("windows", seed=23))

    def test_solver_cli_loads_profile_file_without_overriding_generated_cpu(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            profile = generate_profile("windows", seed=11, hardware_concurrency=6)
            path.write_text(json.dumps(profile))
            args = ["https://solver.test/", "0x4AAAAAADogn3t3_JKwKkgS", "--direct", "--profile-file", str(path)]
            with patch.object(turnstile, "solve_turnstile_details") as solve, redirect_stdout(io.StringIO()):
                solve.return_value = turnstile.TurnstileSolution("offline-test-token", 0.1, 1)
                self.assertEqual(turnstile.main(args), 0)
                self.assertEqual(solve.call_args.kwargs["profile"], profile)
            for value in ("[]", "null", "{broken", "\"linux\""):
                path.write_text(value)
                with patch.object(turnstile, "solve_turnstile_details") as solve, redirect_stderr(io.StringIO()):
                    self.assertEqual(turnstile.main(args), 1)
                    solve.assert_not_called()
            path.unlink()
            with patch.object(turnstile, "solve_turnstile_details") as solve, redirect_stderr(io.StringIO()):
                self.assertEqual(turnstile.main(args), 1)
                solve.assert_not_called()


@unittest.skipUnless((ROOT / "dist/js").is_file(), "build the native runtime first")
class GeneratedProfileRuntimeTests(unittest.TestCase):
    def test_both_profiles_reach_native_main_and_child_realms(self):
        probe = """(() => {
            const gl=document.createElement('canvas').getContext('webgl');
            const gl2=document.createElement('canvas').getContext('webgl2');
            return {ua:navigator.userAgent,platform:navigator.platform,oscpu:navigator.oscpu,
                cpu:navigator.hardwareConcurrency,language:navigator.language,languages:navigator.languages,
                screen:[screen.width,screen.height,screen.availWidth,screen.availHeight],
                dpr:devicePixelRatio,timezone:new Intl.DateTimeFormat().resolvedOptions().timeZone,
                locale:new Intl.NumberFormat().resolvedOptions().locale,
                renderer:gl.getParameter(gl.getExtension('WEBGL_debug_renderer_info').UNMASKED_RENDERER_WEBGL),
                extensions:gl.getSupportedExtensions(),extensions2:gl2.getSupportedExtensions()};
        })()"""
        for os_name in ("linux", "windows"):
            for locale in ("en-US", "zh-CN"):
                profile = generate_profile(os_name, seed=123, locale=locale, hardware_concurrency=6,
                                           screen_size=(1536, 864), device_pixel_ratio=1.25)
                with self.subTest(os=os_name, locale=locale), Context(shell=ROOT / "dist/js", tls="159") as context:
                    context.configure_fingerprint(profile)
                    context.load_page("https://profile.test/", "<!doctype html><iframe></iframe>")
                    context.advance(10)
                    context.set("probe", probe)
                    main, child = context.eval("[eval(probe),frames[0].eval(probe)]")
                    self.assertEqual(main, child)
                    nav = profile["navigator"]
                    self.assertEqual([main[k] for k in ("ua", "platform", "oscpu", "cpu", "language", "languages")],
                                     [nav[k] for k in ("userAgent", "platform", "oscpu", "hardwareConcurrency", "language", "languages")])
                    self.assertEqual(main["screen"], [profile["screen"][k] for k in ("width", "height", "availWidth", "availHeight")])
                    self.assertEqual(main["dpr"], 1.25)
                    self.assertEqual(main["timezone"], profile["locale"]["timezone"])
                    self.assertEqual(main["locale"].split("-")[0], locale.split("-")[0])
                    for key in ("renderer", "extensions", "extensions2"):
                        self.assertEqual(main[key], profile["webgl"][key])
                    self.assertEqual(context.eval("[innerWidth,innerHeight]"),
                                     [profile["viewport"]["width"], profile["viewport"]["height"]])


if __name__ == "__main__":
    unittest.main()
