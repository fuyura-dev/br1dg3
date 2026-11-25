import csv
import io
import json
import runpy
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from importlib import import_module
from pathlib import Path
from unittest.mock import Mock, patch

from experiments import records
from experiments.export import COLUMNS, collect_rows, export_results

# execution sets up the backend import path for a root-directory invocation.
with patch("google.genai.Client"):
    from experiments import execution  # isort: skip
    from app.services.detection.detect import ScanResult
    from app.services.repair import llm
    from app.services.repair import runner as backend_runner
    from app.services.repair.llm import LLMResult, RequestAttempt
    from app.services.repair.runner import RepairRun, Step


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp = self.enterContext(tempfile.TemporaryDirectory())
        self.local = Path(self.temp) / "local"
        self.enterContext(patch.object(records, "LOCAL_ROOT", self.local))
        self.enterContext(redirect_stdout(io.StringIO()))
        self.configuration = {"configuration_id": "test-configuration", "configuration": {"model": "test-model"}}
        self.enterContext(patch.object(execution, "snapshot_configuration", return_value=self.configuration))
        self.dataset = self.local / "datasets/eligible"
        (self.dataset / "passed").mkdir(parents=True)
        self.inventory = self.local / "inventory.csv"
        self.output = self.local / "pilot/test-run"
        self.html = ('<!DOCTYPE html><html lang="en"><head><title>Example</title></head><body>'
                     '<label for="name">Name</label><input id="name"><img id="photo" src="photo.png">'
                     '</body></html>')
        self.violation = {"id": "image-alt", "impact": "critical", "help": "Images need alternative text",
                          "description": "Test issue", "helpUrl": "https://example.test/rule",
                          "nodes": [{"target": ["#photo"], "html": '<img id="photo" src="photo.png">'}]}
        self.inputs()
        self.scan = self.enterContext(patch.object(execution, "scan_with_report", side_effect=self.scan_result))
        self.calls = []
        self.baseline = self.enterContext(patch.object(execution, "run_baseline", side_effect=self.repair("baseline")))
        self.sdg = self.enterContext(patch.object(execution, "run_sdg", side_effect=self.repair("br1dg3")))

    def inputs(self, count=1):
        digest = records.digest(self.html.encode())
        edge_count = len(execution._extract(self.html)[1])
        inventory = [{"filename": "excluded.html", "sha256": "unused"}]
        eligibility = []
        for i in range(count):
            name = f"example_{i}.html"
            (self.dataset / "passed" / name).write_text(self.html)
            inventory.append({"filename": name, "sha256": digest})
            eligibility.append({"filename": name, "sha256": digest, "status": "passed",
                                "original_sdg_edges": edge_count})
        for path, rows in ((self.inventory, inventory), (self.dataset / "results.csv", eligibility)):
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=rows[0])
                writer.writeheader()
                writer.writerows(rows)

    def scan_result(self, html):
        violations = [] if 'alt="Photo"' in html else [self.violation]
        return ScanResult(violations, {"prepared_html_sha256": records.digest(execution.preprocess(html).encode()),
                                       "stylesheet_warnings": [], "axe": {"violations": violations}})

    def repair(self, method, *, accepted=True, thought=2):
        def operation(html, violations, *, on_progress):
            self.calls.append((method, html, violations))
            candidate = execution.preprocess(html).replace('src="photo.png"', 'src="photo.png" alt="Photo"')
            usage = {"total_input_tokens": 10, "total_output_tokens": 5, "total_tokens": 19}
            if thought is not None:
                usage["total_thought_tokens"] = thought
            response = LLMResult(candidate if accepted else "not HTML", True, "completed", "test-model",
                                 10, 5, thought, 19, 0.1, 2,
                                 attempt_records=[RequestAttempt(1, "request_error", 0.1),
                                                  RequestAttempt(2, "completed", 0.1, usage)])
            step = Step("baseline" if method == "baseline" else "v1", "img", ["image-alt"],
                        "applied" if accepted else "not_html", llm=response, generation_attempted=True)
            current = candidate if accepted else execution.preprocess(html)
            on_progress(step, current)
            return RepairRun(current, [step], 0, configuration={
                "configuration_id": "test-configuration", "prepared_input_sha256": records.digest(execution.preprocess(html).encode())})
        return operation

    def prepare(self, documents=None):
        return execution.prepare_run(self.dataset, self.inventory, self.output, documents)

    def rows(self, manifest):
        return collect_rows(self.output, manifest)

    def test_prepare_only_preserves_inventory_ids_and_makes_no_calls(self):
        self.inputs(2)
        manifest = self.prepare()
        self.assertEqual([d["document_id"] for d in manifest["documents"]], ["Document 2", "Document 3"])
        self.assertEqual([d["methods"] for d in manifest["documents"]], [["baseline", "br1dg3"], ["br1dg3", "baseline"]])
        self.scan.assert_not_called()
        self.baseline.assert_not_called()
        self.assertEqual([r["run_status"] for r in self.rows(manifest)], ["not_run"] * 4)
        with self.assertRaisesRegex(ValueError, "new run"):
            self.prepare()

    def test_token_filtered_dataset_preserves_ids_prepared_hashes_and_pairs(self):
        filtering = import_module("experiments.scripts.02_5_filter_token_budget")
        self.inputs(3)
        dataset = self.local / "datasets/token-budget"
        with patch.object(filtering, "count_tokens", side_effect=[60_000, 60_001, 42]):
            filtering.filter_dataset(self.dataset, dataset, None, "test-model")
        manifest = execution.prepare_run(dataset, self.inventory, self.output)
        self.assertEqual([d["document_id"] for d in manifest["documents"]], ["Document 2", "Document 4"])
        for document in manifest["documents"]:
            self.assertEqual(document["prepared_sha256"], document["eligibility"]["prepared_sha256"])
            self.assertEqual(document["eligibility"]["original_sdg_edges"], "1")
            self.assertEqual(set(document["methods"]), {"baseline", "br1dg3"})
        self.assertEqual(len(self.rows(manifest)), 4)
        self.scan.assert_not_called()
        self.baseline.assert_not_called()
        self.sdg.assert_not_called()

    def test_shared_input_alternating_order_raw_export_and_no_regeneration(self):
        self.inputs(2)
        manifest = self.prepare()
        execution.execute_run(self.output)
        self.assertEqual([c[0] for c in self.calls], ["baseline", "br1dg3", "br1dg3", "baseline"])
        self.assertEqual(self.calls[0][1:], self.calls[1][1:])
        self.assertEqual(self.scan.call_count, 6)  # One pretest and two final scans per document.
        rows = self.rows(manifest)
        for row in rows:
            self.assertEqual(row["run_status"], "completed")
            self.assertEqual((row["violations_before"], row["violations_after"]), (1, 0))
            self.assertEqual(row["api_calls"], 1)  # The failed transport attempt is not a completed response.
            self.assertEqual(row["total_tokens"], 19)  # Keep provider total even when components sum to 17.
            self.assertEqual(row["syntactically_valid"], 1)
            self.assertLessEqual(row["structure_seconds"], row["metrics_seconds"])
        self.assertEqual(rows[0]["scan_before_seconds"], rows[1]["scan_before_seconds"])
        execution.execute_run(self.output)
        self.assertEqual(len(self.calls), 4)
        self.assertEqual(self.scan.call_count, 6)
        self.assertEqual(self.rows(manifest), rows)
        output = self.local / "exports/results.csv"
        self.assertEqual(export_results(self.output, output), 4)
        with output.open(newline="") as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(reader.fieldnames, COLUMNS)
            self.assertEqual(len(list(reader)), 4)
        with self.assertRaises(FileExistsError):
            export_results(self.output, output)

    def test_saved_candidate_resumes_scan_without_another_model_call(self):
        self.inputs(2)
        manifest = self.prepare()
        original = self.scan_result
        self.scan.side_effect = [original(self.html), KeyboardInterrupt()]
        with self.assertRaises(KeyboardInterrupt):
            execution.execute_run(self.output)
        self.assertTrue((self.output / "document-0002/baseline/candidate.html").exists())
        self.scan.side_effect = original
        execution.execute_run(self.output, batch_size=1)
        self.assertEqual(self.baseline.call_count, 1)
        self.assertEqual(self.sdg.call_count, 1)
        self.assertEqual([r["run_status"] for r in self.rows(manifest)], ["completed"] * 2 + ["not_run"] * 2)
        attempts = records.read_json(self.output / "document-0002/baseline/scan-after.json")["attempts"]
        self.assertEqual([a["status"] for a in attempts], ["interrupted", "success"])

    def test_interrupted_generation_is_not_repeated_and_known_steps_survive(self):
        manifest = self.prepare()
        complete_step = self.repair("baseline")

        def interrupted(*args, **kwargs):
            complete_step(*args, **kwargs)
            raise KeyboardInterrupt()

        self.baseline.side_effect = interrupted
        with self.assertRaises(KeyboardInterrupt):
            execution.execute_run(self.output)
        with self.assertRaisesRegex(records.ExecutionStopped, "Unfinished generation"):
            execution.execute_run(self.output)
        self.assertEqual(self.baseline.call_count, 1)
        self.sdg.assert_not_called()
        progress = records.read_json(self.output / "document-0002/baseline/progress.json")
        self.assertEqual(progress["known_usage"]["completed_response_count"], 1)
        row = self.rows(manifest)[0]
        self.assertEqual(row["run_status"], "interrupted")
        self.assertIsNone(row["api_calls"])  # A saved prefix is not the complete method's usage.

    def test_interrupted_metric_resumes_only_unfinished_work(self):
        manifest = self.prepare()
        real_structure = execution.calculate_structural_preservation
        with (patch.object(execution, "calculate_structural_preservation", side_effect=KeyboardInterrupt()),
              self.assertRaises(KeyboardInterrupt)):
            execution.execute_run(self.output)
        with patch.object(execution, "calculate_structural_preservation", wraps=real_structure) as structure:
            execution.execute_run(self.output)
        self.assertEqual(structure.call_count, 2)  # Resume baseline, then evaluate BR1DG3.
        self.assertEqual(self.baseline.call_count, 1)
        self.assertEqual(self.scan.call_count, 3)
        self.assertTrue(all(r["run_status"] == "completed" for r in self.rows(manifest)))

    def test_scan_and_metric_failures_preserve_independent_results(self):
        manifest = self.prepare()
        self.scan.side_effect = [self.scan_result(self.html), RuntimeError("Final scan failed"), self.scan_result(self.html.replace('src="photo.png"', 'src="photo.png" alt="Photo"'))]
        with patch.object(execution, "calculate_structural_preservation", side_effect=RuntimeError("TED failed")):
            execution.execute_run(self.output)
        baseline, sdg = self.rows(manifest)
        self.assertEqual(baseline["run_status"], "error")
        self.assertIsNone(baseline["violations_after"])
        self.assertIsNotNone(baseline["scan_after_seconds"])
        self.assertEqual(baseline["syntactically_valid"], 1)
        self.assertEqual(baseline["semantic_status"], "measured")
        self.assertEqual(baseline["api_calls"], 1)
        self.assertEqual(sdg["violations_after"], 0)
        self.assertIsNone(sdg["tree_edit_distance"])
        self.assertEqual(sdg["structure_status"], "error")
        calls_before = self.scan.call_count
        execution.execute_run(self.output, batch_size=1)
        self.assertEqual(self.scan.call_count, calls_before)
        self.assertEqual(self.rows(manifest), [baseline, sdg])

    def test_no_candidate_keeps_completed_reply_usage_and_raw_blanks(self):
        manifest = self.prepare()
        self.baseline.side_effect = self.repair("baseline", accepted=False)
        execution.execute_run(self.output)
        row = self.rows(manifest)[0]
        self.assertEqual(row["generation_status"], "no_candidate")
        self.assertEqual(row["run_status"], "completed")
        self.assertEqual(row["api_calls"], 1)
        for key in ("violations_after", "syntactically_valid", "tree_edit_distance", "sdg_edges_preserved", "scan_after_seconds", "structure_seconds"):
            self.assertIsNone(row[key], key)
        self.assertEqual(row["semantic_status"], "no_candidate_failure_policy")
        self.assertEqual(self.scan.call_count, 2)

    def test_zero_edges_and_missing_tokens_remain_na_and_unknown(self):
        self.html = '<img id="photo" src="photo.png">'
        self.inputs()
        manifest = self.prepare()
        self.baseline.side_effect = self.repair("baseline", thought=None)
        execution.execute_run(self.output)
        baseline, sdg = self.rows(manifest)
        for row in (baseline, sdg):
            self.assertEqual(row["sdg_edges_before"], 0)
            self.assertEqual(row["semantic_status"], "no_relationships")
            self.assertIsNone(row["sdg_edges_preserved"])
        self.assertIsNone(baseline["thought_tokens"])
        self.assertEqual(baseline["usage_status"], "partial")
        self.assertEqual(baseline["total_tokens"], 19)

    def test_pretest_discrepancies_keep_rows_without_paid_calls(self):
        manifest = self.prepare()
        self.violation["nodes"][0]["target"] = ["#missing"]
        execution.execute_run(self.output)
        self.baseline.assert_not_called()
        self.sdg.assert_not_called()
        self.assertEqual(len(self.rows(manifest)), 2)
        self.assertTrue(all(r["run_status"] == "error" for r in self.rows(manifest)))
        self.assertTrue((self.dataset / "passed/example_0.html").exists())

    def test_checksum_and_configuration_changes_stop_before_calls(self):
        manifest = self.prepare()
        prepared = self.output / manifest["documents"][0]["key"] / "prepared.html"
        original = prepared.read_text()
        prepared.write_text("changed")
        with self.assertRaisesRegex(ValueError, "Saved input changed"):
            execution.execute_run(self.output)
        prepared.write_text(original)
        with (patch.object(execution, "snapshot_configuration", return_value={"configuration_id": "different"}),
              self.assertRaisesRegex(ValueError, "configuration/code changed")):
            execution.execute_run(self.output)
        self.scan.assert_not_called()
        self.baseline.assert_not_called()

    def test_selection_paths_and_concurrent_run_lock(self):
        self.inputs(2)
        manifest = self.prepare([3])
        self.assertEqual([d["number"] for d in manifest["documents"]], [3])
        with records.run_lock(self.output):
            with self.assertRaisesRegex(ValueError, "in use"):
                execution.execute_run(self.output)
            with self.assertRaisesRegex(ValueError, "in use"):
                export_results(self.output, self.local / "exports/locked.csv")
        with self.assertRaises(ValueError):
            export_results(self.output, Path(self.temp) / "public.csv")

    def test_real_repair_services_integrate_with_mocked_model_and_scanner(self):
        manifest = self.prepare()
        self.baseline.side_effect = backend_runner.run_baseline
        self.sdg.side_effect = backend_runner.run_sdg

        def reply(prompt):
            image = '<img id="photo" src="photo.png" alt="Photo">'
            if prompt.edit_scope is not None:
                text = json.dumps({"scope": "target", "html": image})
            else:
                text = execution.preprocess(self.html).replace('<img id="photo" src="photo.png">', image)
            return LLMResult(text, True, "completed", "test-model", 10, 5, 0, 15, 0.1, 1)

        def configuration(method, original, prepared):
            return {"configuration_id": "test-configuration", "prepared_input_sha256": records.digest(prepared.encode())}

        with (patch.object(backend_runner, "generate", side_effect=reply) as generate,
              patch.object(backend_runner, "run_configuration", side_effect=configuration)):
            execution.execute_run(self.output)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(self.scan.call_count, 3)
        self.assertTrue(all(r["run_status"] == "completed" for r in self.rows(manifest)))
        self.assertTrue(all(r["api_calls"] == 1 for r in self.rows(manifest)))

    def test_pretest_failed_scan_is_unknown_and_zero_is_an_observation(self):
        for name, response, expected in (("failed", RuntimeError("Scan failed"), None),
                                         ("zero", ScanResult([], {"prepared_html_sha256": records.digest(execution.preprocess(self.html).encode())}), 0)):
            with self.subTest(name=name):
                self.output = self.local / "pilot" / name
                manifest = self.prepare()
                self.scan.side_effect = [response]
                execution.execute_run(self.output)
                for row in self.rows(manifest):
                    self.assertEqual(row["run_status"], "error")
                    self.assertEqual(row["violations_before"], expected)
                self.baseline.assert_not_called()
                self.sdg.assert_not_called()

    def test_export_matches_schema_and_never_loads_backend(self):
        self.prepare()
        with (records.PROJECT_ROOT / "experiments/schema/example-results.csv").open(newline="") as stream:
            self.assertEqual(next(csv.reader(stream)), COLUMNS)
        output = self.local / "exports/offline.csv"
        script = """
import sys
from pathlib import Path
from experiments import records
from experiments.export import export_results
records.LOCAL_ROOT = Path(sys.argv[1])
assert export_results(sys.argv[2], sys.argv[3]) == 2
assert not any(k == 'app' or k.startswith(('app.', 'google.genai')) for k in sys.modules)
"""
        subprocess.run([sys.executable, "-c", script, str(self.local), str(self.output), str(output)],
                       cwd=records.PROJECT_ROOT, check=True, capture_output=True)
        self.assertTrue(output.exists())

    def test_changed_saved_candidate_stops_before_any_new_scan(self):
        self.prepare()
        self.scan.side_effect = [self.scan_result(self.html), KeyboardInterrupt()]
        with self.assertRaises(KeyboardInterrupt):
            execution.execute_run(self.output)
        (self.output / "document-0002/baseline/candidate.html").write_text("changed")
        calls_before = self.scan.call_count
        with self.assertRaisesRegex(ValueError, "Saved candidate changed"):
            execution.execute_run(self.output)
        self.assertEqual(self.scan.call_count, calls_before)
        self.assertEqual(self.baseline.call_count, 1)


    def test_batches_keep_full_manifest_order_and_export_without_repeating_work(self):
        self.inputs(4)
        manifest = self.prepare()
        execution.execute_run(self.output, batch_size=2)
        self.assertEqual([c[0] for c in self.calls], ["baseline", "br1dg3", "br1dg3", "baseline"])
        self.assertEqual([r["run_status"] for r in self.rows(manifest)], ["completed"] * 4 + ["not_run"] * 4)
        saved = {p: p.read_bytes() for key in ("document-0002", "document-0003")
                 for p in (self.output / key).rglob("*.json")}
        partial = self.local / "exports/batch-1.csv"
        self.assertEqual(export_results(self.output, partial), 8)
        with partial.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(rows[4]["run_status"], "not_run")
        self.assertEqual(rows[4]["api_calls"], "")
        execution.execute_run(self.output, batch_size=1)
        self.assertEqual([r["run_status"] for r in self.rows(manifest)], ["completed"] * 6 + ["not_run"] * 2)
        execution.execute_run(self.output)  # Omitting the limit finishes the remaining document.
        execution.execute_run(self.output, batch_size=10)  # Nothing left to execute.
        self.assertEqual(len(self.calls), 8)
        self.assertEqual(self.scan.call_count, 12)
        self.assertTrue(all(r["run_status"] == "completed" for r in self.rows(manifest)))
        self.assertEqual(records.read_json(self.output / "manifest.json"), manifest)
        for path, data in saved.items():
            self.assertEqual(path.read_bytes(), data)

    def test_pretest_failure_uses_one_batch_slot_and_is_not_retried(self):
        self.inputs(3)
        manifest = self.prepare()
        self.scan.side_effect = RuntimeError("Scan failed")
        execution.execute_run(self.output, batch_size=1)
        self.assertEqual([r["run_status"] for r in self.rows(manifest)], ["error"] * 2 + ["not_run"] * 4)
        self.baseline.assert_not_called()
        self.scan.side_effect = self.scan_result
        execution.execute_run(self.output, batch_size=1)
        self.assertEqual([c[0] for c in self.calls], ["br1dg3", "baseline"])
        self.assertEqual(self.scan.call_count, 4)
        self.assertEqual([r["run_status"] for r in self.rows(manifest)], ["error"] * 2 + ["completed"] * 2 + ["not_run"] * 2)

    def test_request_failures_stop_real_services_after_existing_retries(self):
        self.html = self.html.replace('</body>', '<img id="second" src="other.png"></body>')
        self.violation["nodes"].append({"target": ["#second"], "html": '<img id="second" src="other.png">'})
        self.inputs(2)
        self.baseline.side_effect = backend_runner.run_baseline
        self.sdg.side_effect = backend_runner.run_sdg
        failure = RuntimeError("Quota exhausted")
        failure.status_code = 429
        for first in ("baseline", "br1dg3"):
            with self.subTest(first=first):
                self.baseline.reset_mock()
                self.sdg.reset_mock()
                self.output = self.local / "pilot" / first
                manifest = self.prepare()
                manifest["documents"][0]["methods"] = [first, "br1dg3" if first == "baseline" else "baseline"]
                records.write_json(self.output / "manifest.json", manifest)
                with (patch.object(llm.client.interactions, "create", side_effect=failure) as create,
                      patch.object(llm.time, "sleep") as sleep):
                    with self.assertRaisesRegex(records.ExecutionStopped, "Model request failed"):
                        execution.execute_run(self.output, batch_size=2)
                    expected_attempts = llm.controls.MAX_RETRIES + 1
                    self.assertEqual(create.call_count, expected_attempts)
                    self.assertEqual(sleep.call_count, llm.controls.MAX_RETRIES)
                    folder = self.output / "document-0002" / first
                    progress = records.read_json(folder / "progress.json")
                    self.assertEqual(progress["steps"][0]["status"], "llm_error")
                    self.assertEqual(len(progress["steps"][0]["llm"]["attempt_records"]), expected_attempts)
                    attempt = records.last_attempt(records.read_json(folder / "repair.json"))
                    self.assertEqual(attempt["status"], "interrupted")
                    self.assertGreaterEqual(attempt["seconds"], 0)
                    self.assertIn("Model request failed", attempt["error"])
                    with self.assertRaisesRegex(records.ExecutionStopped, "Unfinished generation"):
                        execution.execute_run(self.output, batch_size=2)
                    self.assertEqual(create.call_count, expected_attempts)
                    self.assertEqual(records.last_attempt(records.read_json(folder / "repair.json"))["error"], attempt["error"])
                other = self.sdg if first == "baseline" else self.baseline
                other.assert_not_called()
                rows = self.rows(manifest)
                self.assertEqual([r["run_status"] for r in rows], ["interrupted"] + ["not_run"] * 3)
                self.assertIsNone(rows[0]["api_calls"])

    def test_completed_steps_survive_a_later_request_failure(self):
        self.inputs(2)
        manifest = self.prepare()
        completed_step = self.repair("br1dg3")

        def partial(html, violations, *, on_progress):
            run = completed_step(html, violations, on_progress=on_progress)
            failed = Step("next", "img", ["image-alt"], "llm_error", error="Quota exhausted",
                          generation_attempted=True)
            on_progress(failed, run.fixed_html)
            self.fail("Execution continued after a failed request")

        self.sdg.side_effect = partial
        with self.assertRaises(records.ExecutionStopped):
            execution.execute_run(self.output)
        progress = records.read_json(self.output / "document-0002/br1dg3/progress.json")
        self.assertEqual([s["status"] for s in progress["steps"]], ["applied", "llm_error"])
        self.assertIsNone(progress["known_usage"]["completed_response_count"])
        self.assertEqual(progress["known_usage"]["completed_response_usage"]["known_completed_responses"], 1)
        self.assertIn('alt="Photo"', progress["partial_html"])
        rows = self.rows(manifest)
        self.assertEqual([r["run_status"] for r in rows], ["completed", "interrupted", "not_run", "not_run"])
        self.assertIsNone(rows[1]["api_calls"])
        with self.assertRaises(records.ExecutionStopped):
            execution.execute_run(self.output)
        self.assertEqual(self.baseline.call_count, 1)
        self.assertEqual(self.sdg.call_count, 1)

    def test_cli_batch_size_on_new_and_resumed_runs(self):
        self.inputs(2)
        script = str(records.PROJECT_ROOT / "experiments/scripts/03_run_experiment.py")
        arguments = [script, "--dataset", str(self.dataset), "--inventory", str(self.inventory),
                     "--output", str(self.output), "--batch-size", "1"]
        with patch.object(sys, "argv", arguments):
            runpy.run_path(script, run_name="__main__")
        manifest = records.read_json(self.output / "manifest.json")
        self.assertEqual([r["run_status"] for r in self.rows(manifest)], ["completed"] * 2 + ["not_run"] * 2)
        with patch.object(sys, "argv", [script, "--resume", str(self.output), "--batch-size", "1"]):
            runpy.run_path(script, run_name="__main__")
        self.assertTrue(all(r["run_status"] == "completed" for r in self.rows(manifest)))
        self.assertEqual(len(self.calls), 4)

    def test_invalid_batch_sizes_are_rejected_before_work(self):
        for size in (0, -1):
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, "positive"):
                execution.execute_run(self.output, batch_size=size)
        script = str(records.PROJECT_ROOT / "experiments/scripts/03_run_experiment.py")
        for size in ("0", "-1", "1.5", "invalid"):
            with (self.subTest(size=size), redirect_stderr(io.StringIO()),
                  patch.object(sys, "argv", [script, "--resume", str(self.output), "--batch-size", size]),
                  self.assertRaises(SystemExit) as stopped):
                runpy.run_path(script, run_name="__main__")
            self.assertEqual(stopped.exception.code, 2)
        self.assertFalse(self.output.exists())
        self.scan.assert_not_called()
        self.baseline.assert_not_called()


class StageTests(unittest.TestCase):
    def test_timing_failure_and_hard_interruption_missingness(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "stage.json"
            with patch.object(records.time, "perf_counter", side_effect=[10.0, 13.5]):
                record = records.timed_stage(path, Mock(side_effect=RuntimeError("Failed")))
            self.assertEqual(records.elapsed(record), 3.5)
            self.assertEqual(records.last_attempt(record)["status"], "error")
            records.write_json(path, {"attempts": [{"status": "running", "seconds": None}]})
            record = records.timed_stage(path, lambda: {"ok": True})
            self.assertIsNone(records.elapsed(record))
            self.assertEqual([a["status"] for a in record["attempts"]], ["interrupted", "success"])

    def test_storage_failure_stops_before_operation(self):
        operation = Mock()
        with (patch.object(records, "write_json", side_effect=records.RecordingError("disk full")),
              self.assertRaises(records.RecordingError)):
            records.timed_stage(Path("/nonexistent/stage.json"), operation)
        operation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
