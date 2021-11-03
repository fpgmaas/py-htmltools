import os
from tempfile import TemporaryDirectory
from typing import Union
import textwrap

from htmltools import *


def saved_html(x: Union[Tag, HTMLDocument], lib_prefix: str = "lib") -> str:
    with TemporaryDirectory() as tmpdir:
        f = os.path.join(tmpdir, "index.html")
        x.save_html(f, lib_prefix=lib_prefix)
        return open(f, "r").read()


def test_dep_resolution(snapshot):
    a1_1 = HTMLDependency(
        "a", "1.1", source={"package": None, "subdir": "foo"}, script={"src": "a1.js"}
    )
    a1_2 = HTMLDependency(
        "a", "1.2", source={"package": None, "subdir": "foo"}, script={"src": "a2.js"}
    )
    a1_2_1 = HTMLDependency(
        "a", "1.2.1", source={"package": None, "subdir": "foo"}, script={"src": "a3.js"}
    )
    b1_9 = HTMLDependency(
        "b", "1.9", source={"package": None, "subdir": "foo"}, script={"src": "b1.js"}
    )
    b1_10 = HTMLDependency(
        "b", "1.10", source={"package": None, "subdir": "foo"}, script={"src": "b2.js"}
    )
    c1_0 = HTMLDependency(
        "c", "1.0", source={"package": None, "subdir": "foo"}, script={"src": "c1.js"}
    )
    test = TagList(*[a1_1, b1_9, b1_10, a1_2, a1_2_1, b1_9, b1_10, c1_0])
    assert HTMLDocument(test).render()["html"] == textwrap.dedent(
        """\
        <!DOCTYPE html>
        <html>
          <head>
            <meta charset="utf-8"/>
            <script src="a-1.2.1/a3.js"></script>
            <script src="b-1.10/b2.js"></script>
            <script src="c-1.0/c1.js"></script>
          </head>
          <body></body>
        </html>"""
    )

    assert HTMLDocument(test).render(lib_prefix="libfoo")["html"] == textwrap.dedent(
        """\
        <!DOCTYPE html>
        <html>
          <head>
            <meta charset="utf-8"/>
            <script src="libfoo/a-1.2.1/a3.js"></script>
            <script src="libfoo/b-1.10/b2.js"></script>
            <script src="libfoo/c-1.0/c1.js"></script>
          </head>
          <body></body>
        </html>"""
    )


# Test out renderTags and findDependencies when tags are inline
def test_inline_deps(snapshot):
    a1_1 = HTMLDependency(
        "a", "1.1", source={"package": None, "subdir": "foo"}, script={"src": "a1.js"}
    )
    a1_2 = HTMLDependency(
        "a", "1.2", source={"package": None, "subdir": "foo"}, script={"src": "a2.js"}
    )
    tests = [
        TagList(a1_1, div("foo"), "bar"),
        TagList(a1_1, div("foo"), a1_2, "bar"),
        div(a1_1, div("foo"), "bar"),
        TagList([a1_1, div("foo")], "bar"),
        div([a1_1, div("foo")], "bar"),
    ]
    html_ = "\n\n".join([HTMLDocument(t).render()["html"] for t in tests])
    snapshot.assert_match(html_, "inline_deps")


def test_append_deps(snapshot):
    a1_1 = HTMLDependency(
        "a", "1.1", source={"package": None, "subdir": "foo"}, script={"src": "a1.js"}
    )
    a1_2 = HTMLDependency(
        "a", "1.2", source={"package": None, "subdir": "foo"}, script={"src": "a2.js"}
    )
    b1_0 = HTMLDependency(
        "b", "1.0", source={"package": None, "subdir": "foo"}, script={"src": "b1.js"}
    )
    x = div(a1_1, b1_0)
    x.append(a1_2)
    y = div(a1_1)
    y.append([a1_2, b1_0])
    z = div()
    z.append([a1_1, b1_0])
    z.append(a1_2)
    tests = [x, y, z]
    html_ = "\n\n".join([HTMLDocument(t).render()["html"] for t in tests])
    snapshot.assert_match(html_, "append_deps")


def test_script_input(snapshot):
    def fake_dep(**kwargs):
        return HTMLDependency(
            "a", "1.0", source={"package": None, "subdir": "srcpath"}, **kwargs
        )

    dep1 = fake_dep(
        script={"src": "js/foo bar.js"}, stylesheet={"href": "css/bar foo.css"}
    )
    dep2 = fake_dep(
        script=[{"src": "js/foo bar.js"}], stylesheet=[{"href": "css/bar foo.css"}]
    )
    assert dep1 == dep2
    # Make sure repeated calls to as_html() repeatedly encode
    test = TagList([dep1, dep2])
    for i in range(2):
        assert HTMLDocument(test).render()["html"] == textwrap.dedent(
            """\
            <!DOCTYPE html>
            <html>
              <head>
                <meta charset="utf-8"/>
                <link href="a-1.0/css/bar%20foo.css" rel="stylesheet"/>
                <script src="a-1.0/js/foo%20bar.js"></script>
              </head>
              <body></body>
            </html>"""
        )


def test_head_output():
    a = HTMLDependency(
        "a",
        "1.0",
        source={"package": None, "subdir": "foo"},
        head=tags.script("1 && 1"),
    )
    assert a.as_html_tags().get_html_string() == "<script>1 && 1</script>"

    b = HTMLDependency(
        "a",
        "1.0",
        source={"package": None, "subdir": "foo"},
        head="<script>1 && 1</script>",
    )
    assert b.as_html_tags().get_html_string() == "<script>1 && 1</script>"


def test_meta_output():
    a = HTMLDependency(
        "a",
        "1.0",
        source={"package": None, "subdir": "foo"},
        script={"src": "a1.js"},
        meta={"name": "viewport", "content": "width=device-width, initial-scale=1"},
    )

    b = HTMLDependency(
        "b",
        "2.0",
        source={"package": None, "subdir": "foo"},
        meta=[{"name": "x", "content": "x-value"}, {"name": "y", "content": "y-value"}],
    )

    assert str(a.as_html_tags()) == textwrap.dedent(
        """\
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <script src="a-1.0/a1.js"></script>"""
    )
    assert str(b.as_html_tags()) == textwrap.dedent(
        """\
        <meta name="x" content="x-value"/>
        <meta name="y" content="y-value"/>"""
    )

    # Combine the two in an HTMLDocument and render; all meta tags should show up.
    combined_html = HTMLDocument(TagList(a, b)).render()["html"]
    assert (
        combined_html.find(
            '<meta name="viewport" content="width=device-width, initial-scale=1"/>'
        )
        != -1
    )
    assert combined_html.find('<meta name="x" content="x-value"/>') != -1
    assert combined_html.find('<meta name="y" content="y-value"/>') != -1
