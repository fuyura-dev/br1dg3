"""Secret-free snapshots of local experiment controls and exact model requests."""

import json
import platform
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from app.config import settings
from app.services.detection.detect import RELEVANT_RULES
from app.services.repair import controls, root_view, scope
from app.services.repair.prompt import BASELINE_SYSTEM, SDG_SYSTEM

BACKEND_ROOT = Path(__file__).resolve().parents[3]
PACKAGES = ("google-genai", "httpx", "beautifulsoup4", "networkx", "selenium", "html5lib", "fastapi")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _installed_version(package):
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def snapshot_configuration():
    # Only project source and named assets: never read .env, credentials or data.
    paths = sorted((BACKEND_ROOT / "app").rglob("*.py"))
    paths += [BACKEND_ROOT / "requirements.txt", BACKEND_ROOT / "app/services/detection/axe.min.js"]
    sources = {str(path.relative_to(BACKEND_ROOT)): sha256(path.read_bytes()).hexdigest() for path in paths}
    generation = deepcopy(controls.GENERATION_CONFIG)
    configuration = {
        "model_requested": settings.LLM_MODEL,
        "generation_config": generation,
        "unspecified_generation_options": [name for name in ("temperature", "top_p", "seed", "max_output_tokens")
                                           if name not in generation],
        "unspecified_options_policy": "provider_defaults_not_assumed_or_guaranteed_stable",
        "store": False,
        "sdk_retry_control": "interactions.sdk_configuration.retry_config=None",
        "transport_retry": {
            "max_application_attempts": controls.MAX_RETRIES + 1,
            "delays_seconds": [controls.retry_delay(i) for i in range(controls.MAX_RETRIES)],
            "http_status_codes": sorted(controls.RETRY_STATUS), "exception_names": sorted(controls.RETRY_ERRORS),
            "sdk_internal_retries": False,
            "request_count_basis": "application_attempts",
        },
        "repair_regenerations_after_completed_reply": 0,
        "scope": {
            "parent_characters": scope.BLOCK_CHAR_LIMIT, "parent_elements": scope.BLOCK_ELEMENT_LIMIT,
            "target_characters": scope.TARGET_CHAR_LIMIT, "target_elements": scope.TARGET_ELEMENT_LIMIT,
            "root_view_characters": root_view.ROOT_MARKUP_CHAR_LIMIT,
            "root_literal_characters": root_view.ROOT_LITERAL_CHAR_LIMIT,
            "parent_hops": 1, "output_size_rejection": False,
        },
        "preprocessing": "shared_script_style_removal; evaluation_before_api_restoration",
        "schedule": "fixed_initial_targets_with_current_context",
        "selected_rules": list(RELEVANT_RULES),
        "system_prompts": {"zero_shot": BASELINE_SYSTEM, "sdg": SDG_SYSTEM},
        "runtime": {"python": platform.python_version(), "packages": {name: _installed_version(name) for name in PACKAGES}},
        "source_sha256": sources,
        "experimental_cache_policy": "bypass_required; actual_api_cache_setting_recorded_separately",
    }
    return {"schema_version": 1, "captured_at": utc_now(),
            "configuration_id": fingerprint(configuration), "configuration": configuration}


def run_configuration(method, original, prepared):
    return {**snapshot_configuration(), "method": method,
            "runner_input_sha256": sha256(original.encode("utf-8")).hexdigest(),
            "prepared_input_sha256": sha256(prepared.encode("utf-8")).hexdigest()}


def request_record(payload):
    # The explicit LLM payload contains no API key or transport headers.
    return {"captured_at": utc_now(), "request_sha256": fingerprint(payload), "payload": deepcopy(payload)}
