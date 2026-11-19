import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup, Comment

from app.services.detection.preprocess import (
    preprocess,
    stash_non_essential,
    unstash_non_essential,
)
from app.services.repair.context import ContextExtractor
from app.services.repair.patch import MARKER, apply_reply, outer_html, strip_markers
from app.services.repair.prompt import _shallow_layout_tree, build_sdg_prompt
from app.services.repair.root_view import (
    CONTENT_PREFIX,
    ROOT_MARKUP_CHAR_LIMIT,
    RootViewTooLarge,
)
from app.services.sdg.builder import SDGBuilder
from tests.repair_fixtures import sdg_reply, target_from_prompt

with patch("google.genai.Client"):
    from app.api.repair import _serialize_steps
    from app.services.repair import runner
    from app.services.repair.llm import LLMResult


def wrapped_view(source):
    """Simulate a model wrapping the shown body content without rewriting it."""
    view = BeautifulSoup(_shallow_layout_tree(source.body), "html.parser")
    main = view.new_tag("main")
    for node in list(view.body.contents):
        main.append(node.extract())
    view.body.append(main)
    return str(view)


class TestContainerContent(unittest.TestCase):
    def _apply(self, original, reply):
        soup = BeautifulSoup(original, "html.parser")
        before = outer_html(soup)
        result = apply_reply(soup.find(attrs={MARKER: "v1"}), reply, "v1")
        if not result.applied:
            self.assertEqual(outer_html(soup), before)
        return soup, result

    def test_wrapper_keeps_text_before_between_and_after_children(self):
        original = (
            '<body data-br1dg3="v1">Welcome!<div id="a" data-br1dg3="v2">First</div>'
            'Between<div id="b">Second</div>Thank you.</body>'
        )
        for reply in (
            '<body><main>Welcome!<div id="a">…</div>Between<div id="b">…</div>Thank you.</main></body>',
            '<body><main>…</main></body>',
        ):
            with self.subTest(reply=reply):
                soup, result = self._apply(original, reply)
                self.assertTrue(result.applied)
                self.assertEqual(soup.main.decode_contents(), (
                    'Welcome!<div data-br1dg3="v2" id="a">First</div>'
                    'Between<div id="b">Second</div>Thank you.'
                ))
                self.assertEqual(len(soup.find_all(id="a")), 1)

    def test_comments_remain_between_their_neighbours_inside_a_wrapper(self):
        original = (
            '<body data-br1dg3="v1"><!--before--><div id="a">First</div>'
            '<!--between--><div id="b">Second</div><!--after--></body>'
        )
        for comments in (True, False):
            reply = '<body><main><!--before--><div id="a">…</div><!--between--><div id="b">…</div><!--after--></main></body>'
            if not comments:
                reply = reply.replace('<!--before-->', '').replace('<!--between-->', '').replace('<!--after-->', '')
            with self.subTest(echoed=comments):
                soup, result = self._apply(original, reply)
                if not comments:
                    self.assertFalse(result.applied)
                    self.assertIn("ambiguous_content_placement", result.warnings)
                    continue
                self.assertTrue(result.applied)
                self.assertEqual(soup.main.decode_contents(), (
                    '<!--before--><div id="a">First</div><!--between--><div id="b">Second</div><!--after-->'
                ))

    def test_referenced_hidden_elements_remain_in_sequence(self):
        original = (
            '<body data-br1dg3="v1">Start<div id="a">A</div>'
            '<link href="theme.css" rel="stylesheet"><!--asset--><div id="b">B</div>End</body>'
        )
        soup, result = self._apply(original, wrapped_view(BeautifulSoup(original, "html.parser")))
        self.assertTrue(result.applied)
        self.assertEqual(soup.main.decode_contents(), (
            'Start<div id="a">A</div><link href="theme.css" rel="stylesheet"/><!--asset--><div id="b">B</div>End'
        ))

    def test_mixed_content_in_new_nested_wrappers_is_not_dropped(self):
        soup, result = self._apply(
            '<body data-br1dg3="v1"><div id="content"><span>Keep</span></div></body>',
            '<body><main>Intro<section>Before<div id="content">…</div>After<!--note--></section>Outro</main></body>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.main.decode_contents(), (
            'Intro<section>Before<div id="content"><span>Keep</span></div>After<!--note--></section>Outro'
        ))

    def test_repeated_text_and_comments_are_matched_by_occurrence(self):
        soup, result = self._apply(
            '<body data-br1dg3="v1">Same<!--same--><div id="a">A</div>Same<!--same--><div id="b">B</div>Same</body>',
            '<body><main>Same<!--same--><div id="a">…</div>Same<!--same--><div id="b">…</div>Same</main></body>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.main.decode_contents(), (
            'Same<!--same--><div id="a">A</div>Same<!--same--><div id="b">B</div>Same'
        ))

    def test_echoed_text_is_not_duplicated_by_a_new_collapsed_wrapper(self):
        soup, result = self._apply(
            '<body data-br1dg3="v1">Welcome<div>Content</div>Thanks</body>',
            '<body>Welcome<main>…</main>Thanks</body>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.body.decode_contents(), 'Welcome<main><div>Content</div></main>Thanks')

    def test_new_heading_with_omitted_old_text_is_ambiguous(self):
        _, result = self._apply(
            '<body data-br1dg3="v1">Intro<div id="a">A</div>End</body>',
            '<body><h1>Heading</h1></body>',
        )
        self.assertFalse(result.applied)
        self.assertIn("ambiguous_text_rewrite", result.warnings)

    def test_new_heading_with_explicit_original_text_is_allowed(self):
        soup, result = self._apply(
            '<body data-br1dg3="v1">Intro<div id="a">A</div>End</body>',
            '<body><h1>Heading</h1>Intro<div id="a">…</div>End</body>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.body.decode_contents(), '<h1>Heading</h1>Intro<div id="a">A</div>End')

    def test_bare_text_rewrites_are_rejected_without_appending_old_words(self):
        for reply in ('<body>New instructions</body>', '<body><main>New instructions</main></body>'):
            with self.subTest(reply=reply):
                soup, result = self._apply('<body data-br1dg3="v1">Old instructions</body>', reply)
                self.assertEqual(result.status, "patch_rejected")
                self.assertIn("ambiguous_text_rewrite", result.warnings)
                self.assertEqual(soup.body.string, "Old instructions")

    def test_omitted_text_stays_outside_a_new_wrapper(self):
        soup, result = self._apply(
            '<body data-br1dg3="v1">Before<div id="a">A</div>After</body>',
            '<body><main><div id="a">…</div></main></body>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.body.decode_contents(), 'Before<main><div id="a">A</div></main>After')

    def test_omitted_gap_between_wrapped_or_reordered_anchors_is_rejected(self):
        original = '<body data-br1dg3="v1"><div id="a">A</div>Between<div id="b">B</div></body>'
        for reply in (
            '<body><main><div id="a">…</div><div id="b">…</div></main></body>',
            '<body><div id="b">…</div><div id="a">…</div></body>',
        ):
            with self.subTest(reply=reply):
                _, result = self._apply(original, reply)
                self.assertEqual(result.status, "patch_rejected")
                self.assertIn("ambiguous_content_placement", result.warnings)

    def test_omitted_gap_between_unchanged_anchors_is_preserved(self):
        soup, result = self._apply(
            '<body data-br1dg3="v1"><div id="a">A</div>Between<div id="b">B</div></body>',
            '<body><div id="a">…</div><div id="b">…</div></body>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.body.decode_contents(), '<div id="a">A</div>Between<div id="b">B</div>')

    def test_matched_nested_container_keeps_its_own_mixed_content(self):
        soup, result = self._apply(
            '<body data-br1dg3="v1"><section id="outer">Before<!--a--><div id="inner">Content</div><!--b-->After</section></body>',
            '<body><section id="outer"><main><div id="inner">…</div></main></section></body>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.section.decode_contents(), 'Before<!--a--><main><div id="inner">Content</div></main><!--b-->After')

    def test_collapsed_plain_text_only_body_can_be_wrapped(self):
        soup, result = self._apply('<body data-br1dg3="v1">  Hello &amp; goodbye.  </body>', '<body><main>…</main></body>')
        self.assertTrue(result.applied)
        self.assertEqual(soup.main.string, '  Hello & goodbye.  ')

    def test_original_whitespace_is_retained_when_text_is_echoed(self):
        soup, result = self._apply(
            '<body data-br1dg3="v1">  Hello\n<div id="a">A</div>\tThanks  </body>',
            '<body><main>Hello<div id="a">…</div>Thanks</main></body>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.main.contents[0], '  Hello\n')
        self.assertEqual(soup.main.contents[-1], '\tThanks  ')

    def test_reply_reordering_preserves_original_elements_once(self):
        soup, result = self._apply(
            '<body data-br1dg3="v1"><section id="a"><p>A</p></section><section id="b"><p>B</p></section></body>',
            '<body><section id="b">…</section><section id="a">…</section></body>',
        )
        self.assertTrue(result.applied)
        self.assertEqual([node["id"] for node in soup.body.find_all("section", recursive=False)], ["b", "a"])
        self.assertEqual([node.get_text() for node in soup.find_all("section")], ["B", "A"])

    def test_text_that_looks_like_markup_survives_serialization_and_reparse(self):
        soup, result = self._apply(
            '<body data-br1dg3="v1">A &amp; B &lt;button&gt;literal&lt;/button&gt;'
            '<div id="content" aria-label="A &amp; &quot;B&quot;">Keep</div></body>',
            '<body><main>A &amp; B &lt;button&gt;literal&lt;/button&gt;<div id="content">…</div></main></body>',
        )
        self.assertTrue(result.applied)
        output = strip_markers(outer_html(soup))
        reparsed = BeautifulSoup(output, "html.parser")
        self.assertIsNone(reparsed.button)
        self.assertEqual(reparsed.main.contents[0], 'A & B <button>literal</button>')
        self.assertEqual(reparsed.div["aria-label"], 'A & "B"')

    def test_shared_preprocessing_preserves_entities_across_repeated_passes(self):
        original = (
            '<html><head><title>A &lt;literal&gt; &amp; B</title><style>.x { color: red; }</style></head>'
            '<body aria-label="A &amp; &quot;B&quot;">&lt;button&gt;Text&lt;/button&gt;'
            '<script>const x = "<";</script></body></html>'
        )
        prepared = preprocess(original)
        self.assertEqual(preprocess(prepared), prepared)
        parsed = BeautifulSoup(prepared, "html.parser")
        self.assertEqual(parsed.title.string, 'A <literal> & B')
        self.assertEqual(parsed.body.string, '<button>Text</button>')
        self.assertEqual(parsed.body["aria-label"], 'A & "B"')
        self.assertIsNone(parsed.button)
        self.assertIsNone(parsed.script)
        self.assertIsNone(parsed.style)

    def test_asset_stash_comments_keep_order_through_a_wrapper_repair(self):
        original = '<body>Before<script>const x = "<";</script><div id="a">Text</div><style>.x { color: red; }</style>After</body>'
        stashed, assets = stash_non_essential(original)
        source = BeautifulSoup(preprocess(stashed), "html.parser")
        source.body[MARKER] = "v1"
        soup, result = self._apply(str(source), wrapped_view(source))
        self.assertTrue(result.applied)
        restored = BeautifulSoup(unstash_non_essential(strip_markers(outer_html(soup)), assets), "html.parser")
        self.assertEqual(restored.main.decode_contents(), (
            'Before<script>const x = "<";</script><div id="a">Text</div><style>.x { color: red; }</style>After'
        ))

    def test_tracking_rejection_rolls_back_mixed_content_reconstruction(self):
        _, result = self._apply(
            '<body data-br1dg3="v1">Before<!--keep--><section id="content" data-br1dg3="v2"><img></section>After</body>',
            '<body><main><section id="changed">…</section></main></body>',
        )
        self.assertFalse(result.applied)
        self.assertEqual(result.status, "tracking_rejected")

    def test_shallow_prompt_round_trip_preserves_direct_text_comments_and_long_leaves(self):
        for attributes in ('', ' id="long"'):
            with self.subTest(attributes=attributes):
                long_text = "Long paragraph " * 20
                original = f'<body data-br1dg3="v1">Before &lt;literal&gt;<!--keep--><p{attributes}>{long_text}</p>After</body>'
                source = BeautifulSoup(original, "html.parser")
                reply = _shallow_layout_tree(source.body, max_depth=1)
                parsed_reply = BeautifulSoup(reply, "html.parser")
                self.assertEqual(parsed_reply.body.contents[0], 'Before <literal>')
                self.assertIsInstance(parsed_reply.body.contents[1], Comment)
                self.assertEqual(parsed_reply.p.string, "…")
                soup, result = self._apply(original, reply)
                self.assertTrue(result.applied)
                self.assertEqual(len(soup.find_all("p")), 1)
                self.assertEqual(soup.p.string, long_text)
                self.assertEqual(strip_markers(outer_html(soup)), strip_markers(original))


class TestBoundedRootView(unittest.TestCase):
    def test_long_direct_text_and_comments_round_trip_under_the_limit(self):
        for contents in ("Long instructions " * 800, "<!--" + "Long comment " * 1000 + "-->"):
            with self.subTest(comment=contents.startswith("<!--")):
                soup = BeautifulSoup(f'<body data-br1dg3="v1">{contents}</body>', "html.parser")
                before = outer_html(soup)
                view = _shallow_layout_tree(soup.body)
                self.assertLessEqual(len(view), ROOT_MARKUP_CHAR_LIMIT)
                self.assertIn(CONTENT_PREFIX, view)
                result = apply_reply(soup.body, view, "v1")
                self.assertTrue(result.applied, result)
                self.assertEqual(outer_html(soup), before)
                self.assertNotIn(CONTENT_PREFIX, str(soup))

    def test_wide_document_is_coarsened_without_hiding_root_attributes(self):
        soup = BeautifulSoup(
            '<html data-br1dg3="v1" lang="en"><head><title>Title</title></head>'
            '<body aria-label="Page" role="main">' + '<p>Keep</p>' * 1500 + '</body></html>',
            "html.parser",
        )
        before = outer_html(soup)
        view = _shallow_layout_tree(soup.html)
        shown = BeautifulSoup(view, "html.parser")
        self.assertLessEqual(len(view), ROOT_MARKUP_CHAR_LIMIT)
        self.assertEqual(shown.body.get_text(), "…")
        self.assertEqual(shown.body["aria-label"], "Page")
        self.assertEqual(shown.body["role"], "main")
        self.assertTrue(apply_reply(soup.html, view, "v1").applied)
        self.assertEqual(outer_html(soup), before)

    def test_root_attributes_over_the_limit_are_not_silently_hidden(self):
        soup = BeautifulSoup('<body aria-label="' + 'x' * ROOT_MARKUP_CHAR_LIMIT + '">Text</body>', "html.parser")
        with self.assertRaises(RootViewTooLarge):
            _shallow_layout_tree(soup.body)

    def test_repeated_content_references_keep_each_occurrence_once(self):
        text = "Same long text " * 50
        soup = BeautifulSoup(f'<body data-br1dg3="v1">{text}<!--same--><div>A</div>{text}<!--same--></body>', "html.parser")
        expected = soup.body.decode_contents()
        reply = wrapped_view(soup)
        self.assertTrue(apply_reply(soup.body, reply, "v1").applied)
        self.assertEqual(soup.main.decode_contents(), expected)
        self.assertNotIn(CONTENT_PREFIX, str(soup))

    def test_reference_and_echo_can_retain_two_equal_original_occurrences(self):
        text = "Same long text " * 50
        soup = BeautifulSoup(f'<body data-br1dg3="v1">{text}<div>A</div>{text}</body>', "html.parser")
        expected = outer_html(soup)
        view = BeautifulSoup(_shallow_layout_tree(soup.body), "html.parser")
        view.body.contents[-1].replace_with(text)
        result = apply_reply(soup.body, str(view), "v1")
        self.assertTrue(result.applied, result)
        self.assertEqual(outer_html(soup), expected)

    def test_unknown_modified_duplicate_and_out_of_scope_references_roll_back(self):
        for scenario in ("unknown", "modified", "duplicate", "echo", "scope"):
            with self.subTest(scenario=scenario):
                text = "Original long text " * 50
                soup = BeautifulSoup(f'<body data-br1dg3="v1">{text}<div id="existing">Keep</div></body>', "html.parser")
                before = outer_html(soup)
                view = BeautifulSoup(_shallow_layout_tree(soup.body), "html.parser")
                ref = view.body.contents[0]
                if scenario == "unknown":
                    ref.replace_with(Comment(CONTENT_PREFIX + "unknown__"))
                elif scenario == "modified":
                    ref.replace_with(Comment(str(ref) + "changed"))
                elif scenario == "duplicate":
                    view.body.append(Comment(str(ref)))
                elif scenario == "echo":
                    view.body.append(text)
                else:
                    view.div.clear()
                    view.div.append(ref.extract())
                result = apply_reply(soup.body, str(view), "v1")
                expected = {
                    "unknown": "unknown_content_reference", "modified": "unknown_content_reference",
                    "duplicate": "duplicate_content_reference", "echo": "duplicate_content_reference",
                    "scope": "content_reference_scope",
                }[scenario]
                self.assertEqual(result.status, "patch_rejected")
                self.assertIn(expected, result.warnings)
                self.assertEqual(outer_html(soup), before)

    def test_source_text_resembling_a_reference_is_preserved_without_recursive_expansion(self):
        for depth in (0, 2):
            with self.subTest(depth=depth):
                soup = BeautifulSoup(f'<body data-br1dg3="v1">{CONTENT_PREFIX}literal__</body>', "html.parser")
                before = outer_html(soup)
                view = _shallow_layout_tree(soup.body, max_depth=depth)
                self.assertTrue(apply_reply(soup.body, view, "v1").applied)
                self.assertEqual(outer_html(soup), before)

    def test_long_title_can_be_retained_by_reference_or_explicitly_replaced(self):
        for replace in (False, True):
            with self.subTest(replace=replace):
                soup = BeautifulSoup('<html data-br1dg3="v1"><head><title></title></head><body>Text</body></html>', "html.parser")
                text = "Original title " * 1000
                soup.title.string = text
                view = BeautifulSoup(_shallow_layout_tree(soup.html, show_title=True), "html.parser")
                self.assertLessEqual(len(str(view)), ROOT_MARKUP_CHAR_LIMIT)
                self.assertIn(CONTENT_PREFIX, str(view.title))
                if replace:
                    view.title.string = "New title"
                self.assertTrue(apply_reply(soup.html, str(view), "v1").applied)
                self.assertEqual(soup.title.string, "New title" if replace else text)
                self.assertNotIn(CONTENT_PREFIX, str(soup))


class TestDocumentTitle(unittest.TestCase):
    def _apply(self, original, reply):
        soup = BeautifulSoup(original, "html.parser")
        before = outer_html(soup)
        result = apply_reply(soup.html, reply, "v1")
        if not result.applied:
            self.assertEqual(outer_html(soup), before)
        return soup, result

    def test_title_text_updates_in_place_with_or_without_id(self):
        for attributes in ('', ' id="page-title"'):
            with self.subTest(attributes=attributes):
                original = (
                    '<html data-br1dg3="v1"><head data-info="keep"><meta charset="utf-8">'
                    f'<!--before--><title{attributes}>Old title</title><!--after-->'
                    '<link rel="stylesheet" href="theme.css"><script>const x = "<";</script></head>'
                    '<body>Text</body></html>'
                )
                source = BeautifulSoup(original, "html.parser")
                old_head = list(source.head.contents)
                soup, result = self._apply(original, f'<html><head><title{attributes}>New &amp; better</title></head><body>…</body></html>')
                self.assertTrue(result.applied)
                self.assertEqual(len(soup.find_all("title")), 1)
                self.assertEqual(soup.title.get_text(), "New & better")
                self.assertEqual(soup.head["data-info"], "keep")
                for old, new in zip(old_head, soup.head.contents, strict=True):
                    if getattr(old, "name", None) != "title":
                        self.assertEqual(outer_html(old), outer_html(new))
                self.assertEqual(soup.body.string, "Text")

    def test_empty_title_is_filled(self):
        soup, result = self._apply(
            '<html data-br1dg3="v1"><head><title></title></head><body>Text</body></html>',
            '<html><head><title>Page title</title></head><body>…</body></html>',
        )
        self.assertTrue(result.applied)
        self.assertEqual([t.string for t in soup.find_all("title")], ["Page title"])

    def test_missing_title_is_inserted_without_replacing_metadata(self):
        soup, result = self._apply(
            '<html data-br1dg3="v1"><head><meta charset="utf-8"><!--keep--></head><body>Text</body></html>',
            '<html><head><title>Page title</title><meta charset="changed"></head><body>…</body></html>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.meta["charset"], "utf-8")
        self.assertEqual(len(soup.find_all("meta")), 1)
        self.assertEqual(soup.title.string, "Page title")
        self.assertEqual(str(soup.head.contents[1]), "keep")

    def test_missing_head_is_created_before_body(self):
        soup, result = self._apply(
            '<!DOCTYPE html><html data-br1dg3="v1"><!--keep--><body><p>Text</p></body></html>',
            '<html><head><title>Page title</title></head><body>…</body></html>',
        )
        self.assertTrue(result.applied)
        self.assertEqual(soup.head.title.string, "Page title")
        self.assertEqual([node.name for node in soup.html.find_all(recursive=False)], ["head", "body"])
        self.assertEqual(soup.body.p.string, "Text")
        self.assertTrue(outer_html(soup).startswith("<!DOCTYPE html>"))

    def test_omitted_or_collapsed_title_keeps_the_existing_head(self):
        original = '<html data-br1dg3="v1"><head><meta charset="utf-8"><title>Old</title><!--keep--></head><body>Text</body></html>'
        expected_head = BeautifulSoup(original, "html.parser").head
        for head in ('', '<head>…</head>', '<head><title>…</title></head>'):
            with self.subTest(head=head):
                soup, result = self._apply(original, f'<html lang="en">{head}<body>…</body></html>')
                self.assertTrue(result.applied)
                self.assertEqual(outer_html(soup.head), outer_html(expected_head))

    def test_ambiguous_title_replies_are_rejected_atomically(self):
        cases = [
            ('<title>Old</title>', '<title>One</title><title>Two</title>', 'multiple_reply_titles'),
            ('<title>Old one</title><title>Old two</title>', '<title>New</title>', 'ambiguous_existing_titles'),
        ]
        for original_title, reply_title, warning in cases:
            with self.subTest(warning=warning):
                _, result = self._apply(
                    f'<html data-br1dg3="v1" lang="en"><head>{original_title}</head><body>Text</body></html>',
                    f'<html lang="fr"><head>{reply_title}</head><body>…</body></html>',
                )
                self.assertFalse(result.applied)
                self.assertEqual(result.status, "patch_rejected")
                self.assertIn(warning, result.warnings)

    def test_tracked_title_retains_marker_and_rejects_identity_changes(self):
        original = '<html data-br1dg3="v1"><head><title id="title" data-br1dg3="v2">Old</title></head><body>Text</body></html>'
        soup, result = self._apply(original, '<html><head><title id="title">New</title></head><body>…</body></html>')
        self.assertTrue(result.applied)
        self.assertEqual(soup.title[MARKER], "v2")
        _, rejected = self._apply(original, '<html><head><title id="changed">New</title></head><body>…</body></html>')
        self.assertFalse(rejected.applied)
        self.assertEqual(rejected.status, "tracking_rejected")

    def test_title_context_is_shown_only_for_document_title_issue(self):
        title = 'A <literal> & "quoted" title'
        source = BeautifulSoup('<html id="page"><head><title></title><meta charset="utf-8"></head><body><p>Page</p></body></html>', "html.parser")
        source.title.string = title
        for rule in ("document-title", "html-has-lang"):
            with self.subTest(rule=rule):
                builder = SDGBuilder(str(source), [{"id": rule, "nodes": [{"target": ["#page"]}]}])
                node_id = builder.element_to_id[builder.soup.html]
                prompt = build_sdg_prompt(ContextExtractor.from_builder(builder).extract(node_id), builder.element_to_id)
                markup = prompt.user.split("## Target element [T]\n", 1)[1].split("\n\n##", 1)[0]
                parsed = BeautifulSoup(markup, "html.parser")
                self.assertIsNone(parsed.meta)
                if rule == "document-title":
                    self.assertEqual(parsed.title.get_text(), title)
                    self.assertIsNone(parsed.title.find(True))
                    self.assertIn("## Document title repair", prompt.user)
                else:
                    self.assertIsNone(parsed.title)
                    self.assertEqual(parsed.head.get_text(), "…")


class TestRootContentRunner(unittest.TestCase):
    def _run(self, reply, original=None, violations=None):
        if original is None:
            original = '<html><head><title></title></head><body>Before<img id="photo">After</body></html>'
        if violations is None:
            violations = [
                {"id": "document-title", "nodes": [{"target": ["html"]}]},
                {"id": "image-alt", "nodes": [{"target": ["#photo"]}]},
            ]
        prompts = []

        def generate(prompt):
            prompts.append(prompt.user)
            target = target_from_prompt(prompt)
            if target.name == "html":
                text = reply
            else:
                target["alt"] = "Photo"
                text = str(target)
            return LLMResult(
                text=sdg_reply(text), ok=True, status="completed", model="controlled-test",
                prompt_tokens=10, completion_tokens=5, thought_tokens=0, total_tokens=15,
                latency_s=0.1, attempts=1,
            )

        with patch.object(runner, "generate", side_effect=generate), patch.object(runner.streamer, "log"):
            run = runner.run_sdg(original, violations)
        return run, prompts

    def test_title_and_wrapper_repair_preserve_text_and_continue_to_child(self):
        run, prompts = self._run('<html><head><title>Gallery</title></head><body><main><img id="photo"></main></body></html>')
        self.assertEqual([s.status for s in run.steps], ["applied", "applied"])
        self.assertIn("## Document title repair", prompts[0])
        self.assertEqual(run.generation_status, "accepted")
        output = BeautifulSoup(run.fixed_html, "html.parser")
        self.assertEqual([title.string for title in output.find_all("title")], ["Gallery"])
        self.assertEqual(output.body.decode_contents(), 'Before<main><img alt="Photo" id="photo"/></main>After')
        self.assertNotIn(MARKER, run.fixed_html)

    def test_ambiguous_title_failure_keeps_raw_reply_usage_and_child_execution(self):
        reply = '<html><head><title>One</title><title>Two</title></head><body><main>…</main></body></html>'
        run, _ = self._run(reply)
        self.assertEqual([s.status for s in run.steps], ["patch_rejected", "applied"])
        self.assertEqual(run.generation_status, "partial")
        self.assertEqual(run.failed_steps, 1)
        self.assertEqual(run.total_tokens, 30)
        serialized = _serialize_steps(run)[0]
        self.assertEqual(serialized["raw_reply"], sdg_reply(reply))
        self.assertIsNone(serialized["candidate_html"])
        self.assertIn("multiple_reply_titles", serialized["warnings"])
        output = BeautifulSoup(run.fixed_html, "html.parser")
        self.assertIsNone(output.main)
        self.assertEqual(len(output.find_all("title")), 1)
        self.assertEqual(output.img["alt"], "Photo")

    def test_ambiguous_text_failure_rolls_back_title_and_retains_usage(self):
        reply = '<html><head><title>Gallery</title></head><body>Changed<img id="photo"></body></html>'
        run, _ = self._run(reply)
        self.assertEqual([s.status for s in run.steps], ["patch_rejected", "applied"])
        self.assertEqual(run.generation_status, "partial")
        self.assertEqual(run.total_tokens, 30)
        first = _serialize_steps(run)[0]
        self.assertEqual(first["raw_reply"], sdg_reply(reply))
        self.assertIsNone(first["candidate_html"])
        self.assertIn("ambiguous_text_rewrite", first["warnings"])
        output = BeautifulSoup(run.fixed_html, "html.parser")
        self.assertEqual(output.title.get_text(), "")
        self.assertEqual(output.body.decode_contents(), 'Before<img alt="Photo" id="photo"/>After')

    def test_oversized_root_makes_no_model_call_and_later_child_continues(self):
        original = (
            '<html aria-label="' + 'x' * ROOT_MARKUP_CHAR_LIMIT + '"><head><title></title></head>'
            '<body>Before<img id="photo">After</body></html>'
        )
        run, prompts = self._run("", original=original)
        self.assertEqual([s.status for s in run.steps], ["prompt_too_large", "applied"])
        self.assertEqual(len(prompts), 1)
        self.assertIsNone(run.steps[0].llm)
        self.assertEqual(run.api_calls, 1)
        self.assertEqual(run.requests, 1)
        self.assertEqual(run.total_tokens, 15)
        self.assertEqual(run.failed_steps, 1)
        self.assertEqual(run.generation_status, "partial")
        first = _serialize_steps(run)[0]
        self.assertEqual(first["status"], "prompt_too_large")
        self.assertIsNone(first["raw_reply"])
        self.assertIsNone(first["candidate_html"])
        self.assertIn(str(ROOT_MARKUP_CHAR_LIMIT), first["error"])
        output = BeautifulSoup(run.fixed_html, "html.parser")
        self.assertEqual(output.html["aria-label"], "x" * ROOT_MARKUP_CHAR_LIMIT)
        self.assertEqual(output.title.get_text(), "")
        self.assertEqual(output.img["alt"], "Photo")

    def test_only_oversized_root_retains_document_as_fallback(self):
        original = '<html aria-label="' + 'x' * ROOT_MARKUP_CHAR_LIMIT + '"><head><title></title></head><body>Keep</body></html>'
        run, prompts = self._run("", original=original, violations=[{"id": "document-title", "nodes": [{"target": ["html"]}]}])
        self.assertEqual(prompts, [])
        self.assertEqual(run.generation_status, "no_candidate")
        self.assertTrue(run.fallback_used)
        self.assertEqual(run.failed_steps, 1)
        self.assertIsNone(run.candidate_html)
        self.assertEqual(run.api_calls, 0)
        self.assertEqual(run.total_tokens, 0)
        self.assertEqual(run.fixed_html, preprocess(original))


if __name__ == "__main__":
    unittest.main()
