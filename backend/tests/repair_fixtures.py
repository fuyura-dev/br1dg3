"""Controlled SDG replies using the public prompt/output contract."""

import json

from bs4 import BeautifulSoup

from app.services.repair.patch import MARKER


def sdg_reply(html, scope="target"):
    return json.dumps({"scope": scope, "html": html})


def target_from_prompt(prompt):
    markup = prompt.user.split("## Target element [T]\n", 1)[1].split("\n\n##", 1)[0]
    target = BeautifulSoup(markup, "html.parser").find(True)
    if "## Editable block [B]\n" in prompt.user:
        block = prompt.user.split("## Editable block [B]\n", 1)[1].split("\n\n##", 1)[0]
        target = BeautifulSoup(block, "html.parser").find(attrs={MARKER: target[MARKER]})
    return target
