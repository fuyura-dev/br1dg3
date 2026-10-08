from bs4 import BeautifulSoup
from bs4.formatter import HTMLFormatter

NON_ESSENTIAL = ('script', 'style')


class _AsWritten(HTMLFormatter):

    def attributes(self, tag):
        return [(k, None if v == "" else v) for k, v in tag.attrs.items()]


_AS_WRITTEN = _AsWritten(void_element_close_prefix="")


def preprocess(html: str):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in NON_ESSENTIAL:
        for el in soup.find_all(tag):
            el.extract()
    return soup.decode(formatter=_AS_WRITTEN)

if __name__ == '__main__':
    example = '<script>asdsadsadsad</script><head><style>asdsadsad</style></head>'
    print(preprocess(example))