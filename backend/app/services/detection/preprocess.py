from bs4 import BeautifulSoup

NON_ESSENTIAL = ('script', 'style')

def preprocess(html: str):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in NON_ESSENTIAL:
        for el in soup.find_all(tag):
            el.extract()
    return soup.prettify()

if __name__ == '__main__':
    example = '<script>asdsadsadsad</script><head><style>asdsadsad</style></head>'
    print(preprocess(example))