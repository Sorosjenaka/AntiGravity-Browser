import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / ".agents" / "skills" / "x-social-browser-workflow" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import browser_hub  # noqa: E402
import engage_posts  # noqa: E402
import prompt_setup  # noqa: E402
import verify_work  # noqa: E402


class FakeTab:
    def __init__(self, parent, state_fn):
        self.parent = parent
        self.state_fn = state_fn
        self.url = None

    async def navigate(self, url, timeout=35.0):
        self.url = url

    async def evaluate_dom(self, expr, timeout=20.0):
        return self.state_fn(self.url, expr)

    async def close(self):
        pass


class FakeSession:
    def __init__(self, state_map, fail_once_sid=None):
        self.port = 9999
        self.state_map = state_map
        self.fail_once_sid = fail_once_sid
        self.failed_already = False
        self.restarted = 0
        self.cur_url = None

    async def start(self):
        pass

    async def ping(self, timeout=8.0):
        return True

    async def reset_tab(self):
        pass

    async def open_tab(self):
        return FakeTab(self, self._eval_for_url)

    async def close(self):
        pass

    async def navigate(self, url, timeout=35.0):
        self.cur_url = url
        if self.fail_once_sid and self.fail_once_sid in url and not self.failed_already:
            self.failed_already = True
            raise ConnectionError("simulated Edge/Brave WebSocket drop")

    def _eval_for_url(self, url, expr):
        sid = verify_work._normalize_status_id(url or "")
        st = self.state_map[sid]
        if "VERIFY_POST_JS" in expr or "unlike" in expr and "articlesCount" in expr:
            return {
                "ready": True,
                "profileHref": "/tester",
                "liked": st["liked"],
                "replied": st["replied"],
                "articlesCount": 2,
            }
        if "WAIT_READY_JS" in expr or "alreadyLiked" in expr:
            return {
                "ready": True,
                "terminalMissing": False,
                "profileHref": "/tester",
                "alreadyLiked": st["liked"],
                "hasLike": not st["liked"],
                "hasReply": True,
            }
        if 'button[data-testid="like"]' in expr:
            st["liked"] = True
            return {"x": 100, "y": 200}
        if 'button[data-testid="reply"]' in expr:
            return {"x": 120, "y": 210}
        if "tweetTextarea_0" in expr and "btnX" not in expr:
            return {"x": 150, "y": 250}
        if "btnX" in expr:
            return {
                "ok": True,
                "text": st["reply_text"],
                "disabled": False,
                "ariaDisabled": "false",
                "btnX": 300,
                "btnY": 400,
            }
        if "btn.click()" in expr and "tweetButton" in expr:
            st["replied"] = True
            return None
        if "dialogOpen" in expr:
            return {"dialogOpen": False, "toast": "Balasan Anda telah dikirim", "visibleOwnReply": st["replied"], "btnReady": False}
        if "visibleOwnReply" in expr or "expH" in expr:
            return st["replied"]
        return None

    async def evaluate_dom(self, expr, timeout=20.0):
        return self._eval_for_url(self.cur_url, expr)

    async def click_point(self, x, y, timeout=15.0):
        pass

    async def type_text(self, text, timeout=20.0):
        pass


class WorkflowTests(unittest.TestCase):
    def test_chromium_isolated_prefs_tuning_for_edge_and_brave(self):
        with tempfile.TemporaryDirectory() as td:
            ud_edge = Path(td) / "edge-Agent"
            browser_hub._tune_isolated_chromium_prefs(ud_edge, "edge", "Default")
            prefs_edge = json.loads((ud_edge / "Default" / "Preferences").read_text(encoding="utf-8"))
            self.assertFalse(prefs_edge["background_mode"]["enabled"])
            self.assertFalse(prefs_edge["browser"]["edge_efficiency_mode_enabled"])
            self.assertFalse(prefs_edge["edge"]["sleeping_tabs"]["enabled"])
            self.assertFalse(prefs_edge["startup_boost"]["enabled"])

            ud_brave = Path(td) / "brave-Agent"
            browser_hub._tune_isolated_chromium_prefs(ud_brave, "brave", "Default")
            prefs_brave = json.loads((ud_brave / "Default" / "Preferences").read_text(encoding="utf-8"))
            self.assertFalse(prefs_brave["background_mode"]["enabled"])
            self.assertFalse(prefs_brave["brave"]["p3a"]["enabled"])
            self.assertFalse(prefs_brave["brave"]["stats"]["reporting_enabled"])

    def test_ua_metadata_override_matches_browser_and_version(self):
        edge_meta = browser_hub._build_ua_override_params("Edg/144.0.3719.92", "edge")
        self.assertIn("Edg/144.0.3719.92", edge_meta["userAgent"])
        brands = [b["brand"] for b in edge_meta["userAgentMetadata"]["brands"]]
        self.assertIn("Microsoft Edge", brands)

        brave_meta = browser_hub._build_ua_override_params("Chrome/158.0.8127.92", "brave")
        self.assertIn("Chrome/158.0.8127.92", brave_meta["userAgent"])
        self.assertNotIn("HeadlessChrome", brave_meta["userAgent"])
        self.assertEqual(brave_meta["userAgentMetadata"]["brands"][0]["version"], "158")

    def test_cdp_session_timeout_does_not_hang(self):
        class HangingWS:
            async def send(self, msg):
                pass

            async def recv(self):
                await asyncio.sleep(5.0)
                return "{}"

            async def close(self):
                pass

        async def run():
            sess = browser_hub._CDPSession("ws://127.0.0.1:9222/x", 9222, False, None)
            sess.ws = HangingWS()
            sess._reader_task = asyncio.create_task(sess._reader_loop())
            try:
                with self.assertRaises(asyncio.TimeoutError):
                    await sess._call("Page.enable", {}, timeout=0.15)
            finally:
                await sess.close()

        asyncio.run(run())

    def test_toast_detection_supports_english_and_indonesian(self):
        self.assertTrue(engage_posts._toast_indicates_success("Your post was sent."))
        self.assertTrue(engage_posts._toast_indicates_success("Balasan Anda telah dikirim"))
        self.assertTrue(engage_posts._toast_indicates_error("Something went wrong, try again"))
        self.assertFalse(engage_posts._toast_indicates_error("Your post was sent."))

    def test_prompt_samples_and_cli_custom_prompt_and_audit(self):
        cli_bin = ROOT / "target" / "release" / ("x-social-draft-workflow.exe" if sys.platform.startswith("win") else "x-social-draft-workflow")
        if not cli_bin.exists():
            cli_bin = ROOT / "target" / "debug" / cli_bin.name
        if not cli_bin.exists():
            self.skipTest("Rust CLI binary not built yet")

        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "test.sqlite3"
            subprocess.run([str(cli_bin), "--db", str(db), "init"], check=True, stdout=subprocess.DEVNULL)
            subprocess.run([str(cli_bin), "--db", str(db), "designate-browser", "--label", "Chrome Agent"], check=True, stdout=subprocess.DEVNULL)
            subprocess.run([str(cli_bin), "--db", str(db), "confirm-account", "--handle", "@tester", "--display-name", "Tester"], check=True, stdout=subprocess.DEVNULL)

            pfile = Path(td) / "my_prompt.md"
            pfile.write_text("Write crisp 6-10 word builder replies mentioning project_short.", encoding="utf-8")
            subprocess.run(
                [str(cli_bin), "--db", str(db), "set-prompt", "--file", str(pfile), "--min-words", "6", "--max-words", "10"],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            subprocess.run(
                [str(cli_bin), "--db", str(db), "set-prompt", "--append-rule", "Never mention price targets."],
                check=True,
                stdout=subprocess.DEVNULL,
            )
            out = subprocess.check_output([str(cli_bin), "--db", str(db), "show-prompt", "--json"], text=True)
            state = json.loads(out)
            self.assertEqual(state["source"], "user_custom")
            self.assertIn("Never mention price targets", state["prompt_text"])
            samples = prompt_setup.build_sample_outputs(state)
            self.assertEqual(len(samples), 3)
            for s in samples:
                self.assertGreaterEqual(s["word_count"], 6)
                self.assertLessEqual(s["word_count"], 10)

    def test_engage_fault_recovery_and_parallel_verification(self):
        cli_bin = ROOT / "target" / "release" / ("x-social-draft-workflow.exe" if sys.platform.startswith("win") else "x-social-draft-workflow")
        if not cli_bin.exists():
            cli_bin = ROOT / "target" / "debug" / cli_bin.name
        if not cli_bin.exists():
            self.skipTest("Rust CLI binary not built yet")

        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            db = td_path / "test.sqlite3"
            subprocess.run([str(cli_bin), "--db", str(db), "init"], check=True, stdout=subprocess.DEVNULL)
            subprocess.run([str(cli_bin), "--db", str(db), "designate-browser", "--label", "Edge Agent"], check=True, stdout=subprocess.DEVNULL)
            subprocess.run([str(cli_bin), "--db", str(db), "confirm-account", "--handle", "@tester", "--display-name", "Tester"], check=True, stdout=subprocess.DEVNULL)

            plan = []
            state_map = {}
            for i, sid in enumerate(["1001", "1002", "1003"], 1):
                pfile = td_path / f"post_{i}.txt"
                pfile.write_text(f"Glint milestone update {i} is live for builders.", encoding="utf-8")
                subprocess.run([str(cli_bin), "--db", str(db), "add-post", "--url", f"https://x.com/alice/status/{sid}", "--text-file", str(pfile), "--language", "en"], check=True, stdout=subprocess.DEVNULL)
                dfile = td_path / f"drafts_{i}.json"
                reply = f"Glint milestone {i} makes builder workflows reliably faster"
                dfile.write_text(
                    json.dumps({
                        "project_short": "Glint",
                        "language": "en",
                        "recommended_option": 1,
                        "options": [
                            {"text": reply, "reply_probability": 70, "stars": 4},
                            {"text": f"Glint execution {i} keeps delivering solid production value", "reply_probability": 60, "stars": 3},
                            {"text": f"The Glint approach {i} stands out on metrics", "reply_probability": 55, "stars": 3},
                        ],
                    }),
                    encoding="utf-8",
                )
                saved = json.loads(subprocess.check_output([str(cli_bin), "--db", str(db), "save-drafts", "--post-id", str(i), "--file", str(dfile)], text=True))
                plan.append({
                    "index": i,
                    "post_id": i,
                    "draft_id": saved["draft_ids"][0],
                    "status_id": sid,
                    "url": f"https://x.com/alice/status/{sid}",
                    "reply_text": reply,
                })
                state_map[sid] = {"liked": False, "replied": False, "reply_text": reply}

            plan_path = td_path / "action_plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            out_path = td_path / "engage_results.json"
            verify_out = td_path / "verify_report.json"

            orig_open_eng = engage_posts.open_headless_session
            orig_open_ver = verify_work.open_headless_session
            fake_sess = FakeSession(state_map, fail_once_sid="1002")
            engage_posts.open_headless_session = lambda cfg, port_override=None: fake_sess
            verify_work.open_headless_session = lambda cfg, port_override=None: fake_sess
            try:
                res = asyncio.run(
                    engage_posts.run_engage(
                        cfg={"browser": "edge", "engine": "cdp"},
                        plan=plan,
                        expected_handle="@tester",
                        port_override=None,
                        out_path=out_path,
                        min_delay=0.0,
                        max_delay=0.0,
                        fixed_delay=0.0,
                        verify_parallel=True,
                        verify_concurrency=3,
                        auto_repair=True,
                        verify_out_path=verify_out,
                        cli_path=cli_bin,
                        db_path=db,
                        plan_path=plan_path,
                        strict=True,
                    )
                )
            finally:
                engage_posts.open_headless_session = orig_open_eng
                verify_work.open_headless_session = orig_open_ver

            self.assertEqual(len(res), 3)
            self.assertTrue(all(r["liked"] and r["replied"] for r in res))
            vrep = json.loads(verify_out.read_text(encoding="utf-8"))
            self.assertTrue(vrep["all_passed"])
            self.assertEqual(vrep["passed_count"], 3)


if __name__ == "__main__":
    unittest.main()
