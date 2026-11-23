import json
import logging
import socket
import urllib.parse
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.detection.preprocess import NON_ESSENTIAL, preprocess
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

options = Options()
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--headless=new")

AXE_SCRIPT = (Path(__file__).parent / "axe.min.js").read_text()
STYLESHEET_TIMEOUT_MS = 10_000

RELEVANT_RULES = (
    "aria-allowed-attr",
    "aria-command-name",
    "aria-hidden-focus",
    "aria-input-field-name",
    "aria-required-attr",
    "aria-required-children",
    "aria-required-parent",
    "aria-roles",
    "aria-toggle-field-name",
    "aria-valid-attr",
    "aria-valid-attr-value",
    "button-name",
    "document-title",
    "frame-title",
    "frame-title-unique",
    "html-has-lang",
    "html-lang-valid",
    "image-alt",
    "input-button-name",
    "input-image-alt",
    "label",
    "link-name",
    "select-name",
    "nested-interactive",
    "presentation-role-conflict",
    "scrollable-region-focusable",
    "bypass",
    "skip-link",
    "heading-order",
    "page-has-heading-one",
    "empty-heading",
    "list",
    "listitem",
    "definition-list",
    "dlitem",
    "landmark-one-main",
    "landmark-main-is-top-level",
    "landmark-unique",
    "region",
)

logger = logging.getLogger(__name__)

options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-extensions")


class DetectionError(RuntimeError):
    """The accessibility scan did not produce a usable Axe result."""


@dataclass
class ScanResult:
    """Selected repair inputs and the untouched Axe report from the same scan."""

    violations: list[dict]
    report: dict[str, Any]


def _is_remote_driver_reachable(url: str, timeout: float = 2.0) -> bool:
    """Quickly check if the remote webdriver host:port is accepting connections."""
    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        if not host:
            return False
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def _get_driver():
    if settings.REMOTE_DRIVER_URL:
        if _is_remote_driver_reachable(settings.REMOTE_DRIVER_URL, timeout=2.0):
            try:
                return webdriver.Remote(settings.REMOTE_DRIVER_URL, options=options)
            except Exception as e:  # noqa: BLE001 - retain local-driver fallback
                logger.warning(
                    f"Failed to connect to REMOTE_DRIVER_URL {settings.REMOTE_DRIVER_URL}: {e}. "
                    "Attempting local Chrome."
                )
        else:
            logger.warning(
                f"REMOTE_DRIVER_URL {settings.REMOTE_DRIVER_URL} is not reachable. "
                "Attempting local Chrome."
            )

    try:
        return webdriver.Chrome(options=options)
    except Exception as e:
        raise RuntimeError(
            "Chrome/ChromeDriver is not available. "
            "Please install google-chrome-stable in WSL or set a reachable REMOTE_DRIVER_URL in .env"
        ) from e


def _wait_for_stylesheets(driver):
    """Settle linked CSS, disable unavailable sheets, and return loading warnings."""
    warnings = driver.execute_async_script("""
        const timeoutMs = arguments[0];
        const done = arguments[1];
        const entries = [...document.querySelectorAll('link[rel~="stylesheet" i][href]')]
            .filter(link => !link.disabled && !link.matches('[rel~="alternate" i]')
                && matchMedia(link.media || 'all').matches)
            .map(link => {
                let state = window.__br1dg3Stylesheets.get(link) || 'pending';
                const href = link.getAttribute('href');
                try { new URL(href, document.baseURI); }
                catch { state = 'unresolved_url'; }
                return {link, href, state};
            });
        let finished = false;
        const finish = () => {
            if (finished) return;
            finished = true;
            clearTimeout(timer);
            const warnings = [];
            for (const entry of entries) {
                if (entry.state === 'load') continue;
                // A late response must not apply CSS while Axe is scanning.
                entry.link.disabled = true;
                const status = entry.state === 'pending' ? 'timeout'
                    : entry.state === 'error' ? 'load_error' : entry.state;
                warnings.push({href: entry.href, status});
            }
            requestAnimationFrame(() => requestAnimationFrame(() => done(warnings)));
        };
        const timer = setTimeout(finish, timeoutMs);
        const check = () => {
            if (entries.every(entry => entry.state !== 'pending')) finish();
        };
        for (const entry of entries) {
            if (entry.state !== 'pending') continue;
            for (const type of ['load', 'error']) {
                entry.link.addEventListener(type, () => {
                    entry.state = type;
                    check();
                }, {once: true});
            }
        }
        check();
    """, STYLESHEET_TIMEOUT_MS)
    if not isinstance(warnings, list):
        raise DetectionError("Stylesheet readiness returned an invalid result.")
    return warnings


def scan_with_report(html: str) -> ScanResult:
    """Run Axe once, retaining its report and separate selected-rule violations."""
    html = preprocess(html)
    driver = None
    try:
        driver = _get_driver()
        driver.set_page_load_timeout(10)
        driver.set_script_timeout(15)

        driver.get("data:text/html,")
        driver.execute_script(
            """
            // Capture fast load/error events before inserting the saved HTML.
            window.__br1dg3Stylesheets = new Map();
            for (const type of ['load', 'error']) {
                document.addEventListener(type, event => {
                    const link = event.target;
                    if (link.tagName === 'LINK' && link.matches('[rel~="stylesheet" i]')) {
                        window.__br1dg3Stylesheets.set(link, type);
                    }
                }, true);
            }
            const parser = new DOMParser();
            const doc = parser.parseFromString(arguments[0], 'text/html');
            const root = document.documentElement;
            while (root.attributes.length > 0) {
                root.removeAttribute(root.attributes[0].name);
            }
            if (doc.documentElement) {
                for (const attr of Array.from(doc.documentElement.attributes)) {
                    root.setAttribute(attr.name, attr.value);
                }
                root.innerHTML = doc.documentElement.innerHTML;
            } else {
                root.innerHTML = arguments[0];
            }
            """,
            html,
        )
        stylesheet_warnings = _wait_for_stylesheets(driver)
        driver.execute_script(AXE_SCRIPT)

        raw_res = driver.execute_async_script("""
            try {
                axe.run({}, (err, results) => {
                    if (err) {
                        arguments[0]({ error: String(err) });
                    } else {
                        arguments[0](results || null);
                    }
                });
            } catch (e) {
                arguments[0]({ error: String(e) });
            }
            """)
        if not isinstance(raw_res, dict):
            raise DetectionError("Axe scan returned no result object.")
        if "error" in raw_res:
            raise DetectionError(f"Axe scan failed: {raw_res['error']}")

        violations = raw_res.get("violations")
        if not isinstance(violations, list):
            raise DetectionError(
                "Axe scan returned a missing or invalid violations list."
            )
        for violation in violations:
            if (
                not isinstance(violation, dict)
                or not isinstance(violation.get("id"), str)
                or not violation["id"].strip()
                or not isinstance(violation.get("nodes"), list)
                or not violation["nodes"]
                or any(not isinstance(node, dict) for node in violation["nodes"])
            ):
                raise DetectionError("Axe scan returned a malformed violation record.")

        return ScanResult(
            # Repair code may annotate its inputs; preserve the scan evidence.
            violations=deepcopy([v for v in violations if v["id"] in RELEVANT_RULES]),
            report={
                "selected_rule_ids": list(RELEVANT_RULES),
                "prepared_html_sha256": sha256(html.encode("utf-8")).hexdigest(),
                "removed_elements": list(NON_ESSENTIAL),
                "stylesheet_warnings": stylesheet_warnings,
                "axe": raw_res,
            },
        )
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:  # noqa: BLE001, S110 - cleanup must not hide the scan error
                pass


def detect(html: str) -> list[dict]:
    """Compatibility interface for callers needing only selected-rule violations."""
    return scan_with_report(html).violations


if __name__ == "__main__":
    HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Axe Violations Demo Page</title>
    <style>
        body {
            font-family: sans-serif;
            background-color: #ffffff;
        }
        .bad-contrast {
            color: #999999; 
            background-color: #ffffff;
        }
    </style>
</head>
<body>

    <img src="hero-banner.jpg">

    <h1>Welcome to the Inaccessible Page</h1>
    
    <p class="bad-contrast">
        This light gray text on a white background is very difficult to read.
    </p>

    <a href="https://example.com"></a>

    <form>
        <input type="text" name="username">
        <button type="submit">Submit</button>
    </form>


    <h2>Section Overview</h2>
    <h4>Deeply Nested Sub-item</h4>
    <p>Some content here.</p>


    <button tabindex="3">Click Me Last</button>
    <button tabindex="1">Click Me First</button>

</body>
</html>"""
    print(json.dumps(detect(HTML), indent=2))
