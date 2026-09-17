from app.services.detection.preprocess import preprocess

from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import json

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

def detect(html: str):
    if settings.REMOTE_DRIVER_URL:
        driver = webdriver.Remote(settings.REMOTE_DRIVER_URL, options=options)
    else:
        driver = webdriver.Chrome(options=options)

    driver.get('data:text/html,')

    driver.execute_script(f'document.documentElement.innerHTML = arguments[0]', html)
    driver.execute_script(AXE_SCRIPT)

    violations = driver.execute_async_script(
        'axe.run({}, (err, results) => arguments[0](results))'
    )['violations']

    return list(filter(lambda v: v['id'] in RELEVANT_RULES, violations))

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