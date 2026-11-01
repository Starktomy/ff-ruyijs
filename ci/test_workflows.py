"""Guard fork CI routing and warm/cold dependency-cache build paths."""
import ast
from pathlib import Path
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"


def workflow(name):
    # BaseLoader keeps YAML 1.1's `on`/true/false as strings, as workflow keys
    # and expression literals require, and supports the shared path list alias.
    return yaml.load((WORKFLOWS / name).read_text(), Loader=yaml.BaseLoader)


def condition(source, values):
    """Evaluate the comparisons used by these workflows with fixed inputs."""
    for key, value in values.items():
        source = source.replace(key, repr(value))
    source = source.replace("||", " or ").replace("&&", " and ").strip()
    expression = ast.parse(source, mode="eval")
    allowed = (ast.Expression, ast.BoolOp, ast.Or, ast.And, ast.Compare, ast.Eq,
               ast.NotEq, ast.Constant, ast.Load)
    if any(not isinstance(node, allowed) for node in ast.walk(expression)):
        raise ValueError("unsupported workflow test condition: " + source)
    return eval(compile(expression, "<workflow-condition>", "eval"), {"__builtins__": {}})


class WorkflowTests(unittest.TestCase):
    def test_manual_platform_selection_is_exact(self):
        wheels = workflow("wheels.yml")
        selection = wheels["on"]["workflow_dispatch"]["inputs"]["platform"]
        self.assertEqual(selection["default"], "linux")
        expected = {
            "linux": {"linux"}, "windows": {"windows"}, "macos": {"macos"},
            "windows-macos": {"windows", "macos"}, "all": {"linux", "windows", "macos"},
        }
        self.assertEqual(set(selection["options"]), set(expected))
        for platform, selected in expected.items():
            actual = {name for name, job in wheels["jobs"].items()
                      if condition(job["if"], {"inputs.platform": platform,
                                               "github.event_name": "workflow_dispatch"})}
            self.assertEqual(actual, selected)
        for name, job in wheels["jobs"].items():
            self.assertEqual(job["uses"], f"./.github/workflows/build-{name}.yml")
            self.assertEqual(set(workflow(f"build-{name}.yml")["on"]),
                             {"workflow_call", "workflow_dispatch"})

    def test_version_tags_build_all_platforms_without_branch_or_release_duplicates(self):
        wheels = workflow("wheels.yml")
        self.assertEqual(set(wheels["on"]), {"push", "workflow_dispatch"})
        # A tag-only push filter excludes branch pushes. No release event is
        # registered, so publishing a Release for the same tag cannot rebuild.
        self.assertEqual(wheels["on"]["push"], {"tags": ["v*"]})
        selected = {name for name, job in wheels["jobs"].items()
                    if condition(job["if"], {"inputs.platform": "", "github.event_name": "push"})}
        self.assertEqual(selected, {"windows", "macos", "linux"})
        self.assertIn("github.ref", wheels["concurrency"]["group"])
        self.assertIn("'all'", wheels["concurrency"]["group"])

    def test_each_selected_platform_uses_one_vm_with_the_installed_wheel_test(self):
        groups = set()
        for platform in ("windows", "macos", "linux"):
            config = workflow(f"build-{platform}.yml")
            self.assertEqual(len(config["jobs"]), 1)
            job = next(iter(config["jobs"].values()))
            self.assertIn("runs-on", job)
            self.assertNotIn("needs", job)
            self.assertNotIn("matrix", job.get("strategy", {}))
            self.assertLessEqual(int(job["timeout-minutes"]), 360)
            steps = job["steps"]
            self.assertEqual(sum(step.get("uses") == "actions/checkout@v4" for step in steps), 1)
            self.assertEqual(sum(step.get("id") == "firefox" for step in steps), 1)
            self.assertTrue(any(step.get("name") == "Test the installed wheel" for step in steps))
            self.assertTrue(any(step.get("uses") == "actions/upload-artifact@v4" for step in steps))
            self.assertEqual(config["concurrency"]["cancel-in-progress"], "true")
            group = config["concurrency"]["group"]
            self.assertNotIn(group, groups)
            groups.add(group)

    def test_windows_macos_build_only_missing_donors_and_save_before_project_build(self):
        for platform in ("windows", "macos"):
            steps = next(iter(workflow(f"build-{platform}.yml")["jobs"].values()))["steps"]
            caches = {step["id"]: step for step in steps if step.get("id") in ("js-cache", "browser-cache")}
            self.assertEqual(set(caches), {"js-cache", "browser-cache"})
            for cache in caches.values():
                self.assertEqual(cache["uses"], "actions/cache/restore@v4")
                self.assertNotEqual(cache["with"].get("fail-on-cache-miss"), "true")
            # All combinations: a warm donor never runs a build; a cold donor
            # runs exactly once, while toolchain bootstrap covers a restored JS.
            for js_hit in ("true", "false"):
                for browser_hit in ("true", "false"):
                    values = {"steps.js-cache.outputs.cache-hit": js_hit,
                              "steps.browser-cache.outputs.cache-hit": browser_hit}
                    builds = [step for step in steps if "on cache miss" in step.get("name", "")]
                    active = {step["name"] for step in builds if condition(step["if"], values)}
                    self.assertEqual("Build SpiderMonkey on cache miss" in active, js_hit != "true")
                    self.assertEqual("Build Skia and NSS on cache miss" in active, browser_hit != "true")
                    bootstrap = next(step for step in steps if step.get("name", "").startswith("Bootstrap toolchains"))
                    self.assertEqual(condition(bootstrap["if"], values), js_hit == "true")
            native_index = next(index for index, step in enumerate(steps)
                                if re.match(r"Build (js.exe|dist/js)", step.get("name", "")))
            for cache_id, cache in caches.items():
                build_name = "Build SpiderMonkey on cache miss" if cache_id == "js-cache" else "Build Skia and NSS on cache miss"
                build_index = next(index for index, step in enumerate(steps) if step.get("name") == build_name)
                save_index, save = next((index, step) for index, step in enumerate(steps)
                                       if step.get("uses") == "actions/cache/save@v4"
                                       and step["with"]["path"] == cache["with"]["path"])
                self.assertLess(build_index, save_index)
                self.assertLess(save_index, native_index)
                self.assertEqual(save["if"], f"steps.{cache_id}.outputs.cache-hit != 'true'")
                self.assertIn(f"steps.{cache_id}.outputs.cache-primary-key", save["with"]["key"])

    def test_push_pr_checks_are_small_cancel_superseded_runs_and_skip_docs(self):
        config = workflow("ci.yml")
        self.assertEqual(set(config["on"]), {"push", "pull_request", "workflow_dispatch"})
        paths = config["on"]["push"]["paths"]
        self.assertEqual(paths, config["on"]["pull_request"]["paths"])
        self.assertIn(".github/workflows/**", paths)
        self.assertIn("src/**", paths)
        self.assertIn("python/**", paths)
        self.assertNotIn("docs/**", paths)
        self.assertNotIn("**", paths)
        self.assertEqual(len(config["jobs"]), 1)
        job = next(iter(config["jobs"].values()))
        self.assertTrue(job["runs-on"].startswith("ubuntu"))
        self.assertNotIn("strategy", job)
        self.assertLessEqual(int(job["timeout-minutes"]), 10)
        self.assertEqual(config["concurrency"]["cancel-in-progress"], "true")
        commands = "\n".join(step.get("run", "") for step in job["steps"])
        self.assertIn("ci.test_workflows", commands)
        self.assertNotIn("pip install ruyijs", commands)
        self.assertNotIn("ci/firefox/build.sh", commands)
        self.assertNotIn("tools/build", commands)


if __name__ == "__main__":
    unittest.main()
