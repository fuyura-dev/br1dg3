
import json
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from app.config import settings

options = Options()
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--headless=new")

AXE_SCRIPT = (Path(__file__).parent / 'axe.min.js').read_text()

RELEVANT_RULES = (
    "aria-allowed-attr",
    "aria-command-name",
    "aria-hidden-focus",
    "aria-input-field-name",
    "aria-required-attr",
    "aria-required-children",
    "aria-required-parent",
    "aria-roles",
    "aria-tab-name",
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

import logging
import socket
import urllib.parse

logger = logging.getLogger(__name__)

options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-extensions")


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
            except Exception as e:
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


def detect(html: str):
    driver = None
    try:
        driver = _get_driver()
        driver.set_page_load_timeout(10)
        driver.set_script_timeout(15)

        driver.get('data:text/html,')
        driver.execute_script('document.documentElement.innerHTML = arguments[0]', html)
        driver.execute_script(AXE_SCRIPT)

        violations = driver.execute_async_script(
            'axe.run({}, (err, results) => arguments[0](results))'
        )['violations']

        return list(filter(lambda v: v['id'] in RELEVANT_RULES, violations))
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == '__main__':
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