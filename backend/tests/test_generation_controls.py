import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx

from app.services.repair import configuration, controls, scope
from app.services.repair.configuration import fingerprint, snapshot_configuration
from app.services.repair.prompt import Prompt
from scripts.snapshot_config import main as snapshot_main

with patch("google.genai.Client"):
    from app.api import repair as repair_api
    from app.services.repair import failed_runs, llm, runner


class TestConfigurationSnapshots(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(configuration.settings, "LLM_MODEL", "test-model"))
        self.enterContext(patch.object(runner.streamer, "log"))

    def test_id_is_stable_across_capture_time_and_excludes_secrets(self):
        with patch.object(configuration.settings, "LLM_API_KEY", "SECRET_NEVER_EXPORT"):
            with patch.object(configuration, "utc_now", return_value="first"):
                first = snapshot_configuration()
            with patch.object(configuration, "utc_now", return_value="second"):
                second = snapshot_configuration()
        self.assertEqual(first["configuration_id"], second["configuration_id"])
        self.assertNotEqual(first["captured_at"], second["captured_at"])
        serialized = json.dumps(first)
        self.assertNotIn("SECRET_NEVER_EXPORT", serialized)
        self.assertNotIn("LLM_API_KEY", serialized)
        self.assertNotIn(".env", serialized)
        self.assertEqual(first["configuration"]["model_requested"], "test-model")

    def test_model_generation_scope_and_retry_changes_change_identity(self):
        original = snapshot_configuration()["configuration_id"]
        changes = [patch.object(configuration.settings, "LLM_MODEL", "another-model"),
                   patch.dict(controls.GENERATION_CONFIG, {"temperature": 0.7}),
                   patch.object(scope, "BLOCK_CHAR_LIMIT", 2999),
                   patch.object(controls, "MAX_RETRIES", 2)]
        for change in changes:
            with change:
                self.assertNotEqual(snapshot_configuration()["configuration_id"], original)

    def test_sources_and_exact_system_prompts_affect_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "app/services/detection").mkdir(parents=True)
            source = root / "app/source.py"
            source.write_text("value = 1\n")
            (root / "requirements.txt").write_text("example==1\n")
            (root / "app/services/detection/axe.min.js").write_text("example axe")
            with patch.object(configuration, "BACKEND_ROOT", root):
                original = snapshot_configuration()
                source.write_text("value = 2\n")
                changed = snapshot_configuration()
                self.assertNotEqual(original["configuration_id"], changed["configuration_id"])
                with patch.object(configuration, "SDG_SYSTEM", "Different instructions"):
                    self.assertNotEqual(snapshot_configuration()["configuration_id"], changed["configuration_id"])

    def test_unset_options_are_not_misrepresented_as_explicit_settings(self):
        config = snapshot_configuration()["configuration"]
        self.assertEqual(config["generation_config"], {"thinking_level": "minimal"})
        self.assertIn("seed", config["unspecified_generation_options"])
        self.assertIn("max_output_tokens", config["unspecified_generation_options"])
        self.assertFalse(config["transport_retry"]["sdk_internal_retries"])
        self.assertEqual(config["transport_retry"]["max_application_attempts"], 4)
        self.assertEqual(config["transport_retry"]["delays_seconds"], [1, 2, 4])
        self.assertEqual(config["scope"]["parent_characters"], 3000)
        self.assertEqual(config["scope"]["parent_elements"], 30)
        self.assertFalse(config["scope"]["output_size_rejection"])

    def test_both_methods_record_same_shared_configuration_without_generation(self):
        with patch.object(runner, "generate") as generate:
            sdg = runner.run_sdg('<p>Keep</p>', [])
            baseline = runner.run_baseline('<p>Keep</p>', [])
        generate.assert_not_called()
        self.assertEqual(sdg.configuration["configuration_id"], baseline.configuration["configuration_id"])
        self.assertEqual(sdg.configuration["prepared_input_sha256"], baseline.configuration["prepared_input_sha256"])
        self.assertEqual(sdg.configuration["method"], "sdg")
        self.assertEqual(baseline.configuration["method"], "zero_shot")

    def test_skipped_oversized_target_keeps_configuration(self):
        with patch.object(runner, "generate") as generate:
            run = runner.run_sdg('<div id="large">' + 'x' * 8100 + '</div>',
                                 [{"id": "region", "nodes": [{"target": ["#large"]}]}])
        generate.assert_not_called()
        self.assertEqual(run.steps[0].status, "prompt_too_large")
        self.assertEqual(run.configuration["configuration_id"], snapshot_configuration()["configuration_id"])

    def test_cli_capture_check_drift_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            path = Path(directory) / "config.json"
            snapshot_main(["--output", str(path)])
            original = path.read_bytes()
            snapshot_main(["--check", str(path)])
            with self.assertRaises(FileExistsError):
                snapshot_main(["--output", str(path)])
            self.assertEqual(path.read_bytes(), original)
            with (patch.object(controls, "MAX_RETRIES", 2), contextlib.redirect_stderr(io.StringIO()),
                  self.assertRaises(SystemExit) as failure):
                snapshot_main(["--check", str(path)])
            self.assertEqual(failure.exception.code, 1)

    def test_cli_rejects_edited_manifest(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stderr(io.StringIO()):
            saved = snapshot_configuration()
            saved["configuration"]["model_requested"] = "changed-without-rehashing"
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(saved))
            with self.assertRaises(SystemExit) as failure:
                snapshot_main(["--check", str(path)])
            self.assertEqual(failure.exception.code, 1)


class TestRequestEvidence(unittest.TestCase):
    def setUp(self):
        self.create = Mock(return_value=SimpleNamespace(status="completed", output_text="<p>ok</p>",
                                                       usage=None, model="provider-model"))
        self.enterContext(patch.object(llm, "client", SimpleNamespace(interactions=SimpleNamespace(create=self.create))))
        self.enterContext(patch.object(runner.streamer, "log"))
        self.enterContext(patch.object(runner, "generate", llm.generate))

    def test_exact_prompt_and_requested_settings_are_retained(self):
        result = llm.generate(Prompt("System instructions", 'HTML with "quotes" and é'))
        self.assertEqual(result.request["payload"], self.create.call_args.kwargs)
        self.assertEqual(result.request["request_sha256"], fingerprint(result.request["payload"]))
        self.assertEqual(result.response_model, "provider-model")
        self.assertNotIn("api_key", result.request["payload"])
        self.assertFalse(result.request["payload"]["store"])
        with patch.dict(controls.GENERATION_CONFIG, {"thinking_level": "high"}):
            self.assertEqual(result.request["payload"]["generation_config"]["thinking_level"], "minimal")

    def test_terminal_failure_keeps_exact_attempted_request(self):
        self.create.side_effect = ValueError("Controlled error")
        with self.assertRaises(llm.LLMRequestError) as failure:
            llm.generate(Prompt("System", "Input"))
        record = failure.exception.result
        self.assertEqual(record.request["payload"], self.create.call_args.kwargs)
        self.assertIsNone(record.response_model)

    def test_response_and_saved_failure_keep_run_and_request_evidence(self):
        run = runner.run_baseline('<p>old</p>', [{"id": "region", "nodes": []}])
        response = repair_api.RepairResponse(fixed_html=run.fixed_html, issues_before=1, issues_after=0,
                                             issues_fixed=1, summary="Test", configuration=run.configuration,
                                             steps=repair_api._serialize_steps(run))
        self.assertEqual(response.configuration, run.configuration)
        self.assertEqual(response.steps[0]["llm"]["request"], run.steps[0].llm.request)
        with tempfile.TemporaryDirectory() as directory, patch.object(failed_runs, "FAILED_RUNS_DIR", Path(directory)):
            record_id = failed_runs.save_failed_run(original_html='<p>old</p>', evaluation_original_html='<p>old</p>',
                                                    use_sdg=False, violations_before=[], run=run,
                                                    error=RuntimeError("Scan failed"))
            saved = json.loads((Path(directory) / f"{record_id}.json").read_text())
        self.assertEqual(saved["repair_run"]["configuration"], run.configuration)
        self.assertEqual(saved["repair_run"]["steps"][0]["llm"]["request"], run.steps[0].llm.request)


class TestRealSDKTransport(unittest.TestCase):
    def test_one_sdk_invocation_has_no_hidden_retry(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(503, json={"error": {"code": 503, "message": "Controlled", "status": "UNAVAILABLE"}})
        with (llm.create_client("test-not-a-real-key", http_options={"client_args": {"transport": httpx.MockTransport(handler)}}) as client,
              self.assertRaises(Exception) as failure):
            client.interactions.create(model="test-model", input="Test", store=False)
        self.assertEqual(getattr(failure.exception, "status_code", None), 503)
        self.assertEqual(len(calls), 1)

    def test_wrapper_and_real_sdk_agree_on_four_failed_attempts(self):
        for failure_type in ("503", "timeout", "connection"):
            with self.subTest(failure=failure_type):
                calls = []
                def handler(request, calls=calls, failure_type=failure_type):
                    calls.append(request)
                    if failure_type == "timeout":
                        raise httpx.ReadTimeout("Controlled timeout", request=request)
                    if failure_type == "connection":
                        raise httpx.ConnectError("Controlled connection failure", request=request)
                    return httpx.Response(503, json={"error": {"code": 503, "message": "Controlled", "status": "UNAVAILABLE"}})
                with (llm.create_client("test-not-a-real-key", http_options={"client_args": {"transport": httpx.MockTransport(handler)}}) as client,
                      patch.object(llm, "client", client), patch.object(llm.time, "sleep") as sleep,
                      self.assertRaises(llm.LLMRequestError) as failure):
                    llm.generate(Prompt("System", "Input"))
                self.assertEqual(failure.exception.result.attempts, 4)
                self.assertEqual(len(calls), 4)
                self.assertEqual(sleep.call_count, 3)


if __name__ == "__main__":
    unittest.main()
