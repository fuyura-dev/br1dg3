import re

from bs4 import BeautifulSoup
from bs4.formatter import HTMLFormatter

NON_ESSENTIAL = ('script', 'style')
NON_ESSENTIAL_PATTERN = re.compile(r"<(script|style)\b[^>]*>(?:.*?</\1>|)", re.DOTALL | re.IGNORECASE)


class _AsWritten(HTMLFormatter):

    def attributes(self, tag):
        return [(k, None if v == "" else v) for k, v in tag.attrs.items()]


_AS_WRITTEN = _AsWritten(void_element_close_prefix="")


def stash_non_essential(html: str) -> tuple[str, list[str]]:
    if not html or not isinstance(html, str):
        return html, []

    stashed: list[str] = []

    def _stash(match):
        idx = len(stashed)
        stashed.append(match.group(0))
        return f"<!--__BR1DG3_STASH_{idx}__-->"

    stashed_html = NON_ESSENTIAL_PATTERN.sub(_stash, html)
    return stashed_html, stashed


def unstash_non_essential(html: str, stashed: list[str]) -> str:
    if not html or not stashed:
        return html

    unrestored: list[str] = []
    for idx, snippet in enumerate(stashed):
        marker = f"<!--__BR1DG3_STASH_{idx}__-->"
        if marker in html:
            html = html.replace(marker, snippet)
        else:
            unrestored.append(snippet)

    for snippet in unrestored:
        is_style = re.match(r"<\s*style\b", snippet, re.IGNORECASE) is not None
        if is_style:
            head_close = re.search(r"</head\s*>", html, re.IGNORECASE)
            if head_close:
                pos = head_close.start()
                html = html[:pos] + snippet + "\n" + html[pos:]
                continue
            body_open = re.search(r"<body\b[^>]*>", html, re.IGNORECASE)
            if body_open:
                pos = body_open.start()
                html = html[:pos] + snippet + "\n" + html[pos:]
                continue

        body_close = re.search(r"</body\s*>", html, re.IGNORECASE)
        if body_close:
            pos = body_close.start()
            html = html[:pos] + snippet + "\n" + html[pos:]
        else:
            html = html + "\n" + snippet

    return html


def preprocess(html: str):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in NON_ESSENTIAL:
        for el in soup.find_all(tag):
            el.extract()
    return soup.decode(formatter=_AS_WRITTEN)

if __name__ == '__main__':
    example = '<script>asdsadsadsad</script><head><style>asdsadsad</style></head>'
    print(preprocess(example))