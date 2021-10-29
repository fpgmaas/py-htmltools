import os
import sys
import shutil
import tempfile
from pathlib import Path
from copy import copy, deepcopy
import urllib.parse
import webbrowser
from typing import (
    Iterable,
    Optional,
    Union,
    List,
    Dict,
    Callable,
    Any,
    TypeVar,
    cast,
)

if sys.version_info >= (3, 8):
    from typing import TypedDict, SupportsIndex, Protocol, runtime_checkable
else:
    from typing_extensions import TypedDict, SupportsIndex, Protocol, runtime_checkable

from packaging.version import Version


from .util import (
    ensure_http_server,
    _package_dir,  # type: ignore
    _html_escape,  # type: ignore
    _flatten,  # type: ignore
)

__all__ = (
    "TagList",
    "Tag",
    "HTMLDocument",
    "HTML",
    "MetadataNode",
    "HTMLDependency",
    "RenderedHTML",
    "TagAttrArg",
    "TagChildArg",
    "TagChild",
    "TagFunction",
    "head_content",
)


class RenderedHTML(TypedDict):
    dependencies: List["HTMLDependency"]
    html: str


# MetadataNode objects are not shown when a Tag tree is rendered to HTML text. They can
# be used to carry information that doesn't fit into the normal HTML tree structure,
# such as `HTMLDependency` objects.
#
# Note that when `x.tagify()` is called on the parent of a MetadataNode, it calls copy()
# on MetadataNode; when copied, the resulting object should be completely independent of
# the original. This may require implementing a custom `__copy__` method.
class MetadataNode:
    pass


T = TypeVar("T")

TagT = TypeVar("TagT", bound="Tag")

# Types of objects that can be a child of a tag.
TagChild = Union["Tagifiable", "Tag", MetadataNode, str]

# Types that can be passed as args to TagList() and tag functions.
TagChildArg = Union[TagChild, "TagList", int, float, None, Iterable["TagChildArg"]]

# Types that can be passed in as attributes to tag functions.
TagAttrArg = Union[str, int, float, bool, None]


# Objects with tagify() methods are considered Tagifiable.
@runtime_checkable
class Tagifiable(Protocol):
    def tagify(self) -> Union["Tag", MetadataNode, str]:
        ...


# Tag functions, like div(), span(), etc.
@runtime_checkable
class TagFunction(Protocol):
    def __call__(
        self,
        *args: TagChildArg,
        children: Optional[List[TagChildArg]] = None,
        **kwargs: TagAttrArg,
    ) -> "Tag":
        ...


# =============================================================================
# TagList class
# =============================================================================
class TagList(List[TagChild]):
    """
    Create an HTML tag list (i.e., a fragment of HTML)

    Methods:
    --------
        show: Preview as a complete HTML document.
        save_html: Save to a HTML file.
        append: Append children to existing children.
        extend: Append an iterable child to existing children.
        insert: Add children into a specific child index.
        render: Returns the HTML string and list of dependencies.
        get_html_string: the HTML string.
        get_dependencies: the HTMLDependency()s.
        tagify: Converts any tagifiable children to Tag/TagList objects.

    Examples:
    ---------
        >>> from htmltools import *
        >>> x = TagList("hello", div(id="foo", class_="bar"))
        >>> x
        >>> print(x)
    """

    def __init__(self, *args: TagChildArg) -> None:
        super().__init__(_tagchildargs_to_tagchilds(args))

    def extend(self, x: Iterable[TagChildArg]) -> None:
        super().extend(_tagchildargs_to_tagchilds(x))

    def append(self, *args: TagChildArg) -> None:  # type: ignore
        # Note that if x is a list or tag_list, it could be flattened into a list of
        # TagChildArg or TagChild objects, and the list.append() method only accepts one
        # item, so we need to wrap it into a list and send it to .extend().
        self.extend(args)

    def insert(self, index: SupportsIndex, x: TagChildArg) -> None:
        self[index:index] = _tagchildargs_to_tagchilds([x])

    def tagify(self) -> "TagList":
        cp = copy(self)
        for i, child in enumerate(cp):
            if isinstance(child, Tagifiable):
                cp[i] = child.tagify()
            elif isinstance(child, MetadataNode):
                cp[i] = copy(child)
        return cp

    def save_html(self, file: str, libdir: Optional[str] = None) -> str:
        return HTMLDocument(self).save_html(file, libdir)

    def render(self) -> RenderedHTML:
        cp = self.tagify()
        deps = cp.get_dependencies()
        return {"dependencies": deps, "html": cp.get_html_string()}

    def get_html_string(self, indent: int = 0, eol: str = "\n") -> "HTML":
        html_ = ""
        line_prefix = ""
        for child in self:
            if isinstance(child, Tag):
                html_ += line_prefix + child.get_html_string(indent, eol)
            elif isinstance(child, MetadataNode):
                continue
            elif isinstance(child, Tagifiable):
                raise RuntimeError(
                    "Encountered a non-tagified object. x.tagify() must be called before x.render()"
                )
            else:
                # If we get here, x must be a string.
                html_ += line_prefix + ("  " * indent) + _normalize_text(child)

            if line_prefix == "":
                line_prefix = eol
        return HTML(html_)

    def get_dependencies(self, *, dedup: bool = True) -> List["HTMLDependency"]:
        deps: List[HTMLDependency] = []
        for x in self:
            if isinstance(x, HTMLDependency):
                deps.append(x)
            elif isinstance(x, Tag):
                # When we recurse, don't deduplicate at every node. We only need to do
                # that once, at the top level.
                deps.extend(x.get_dependencies(dedup=False))

        if dedup:
            return _resolve_dependencies(deps)
        else:
            return deps

    def show(self, renderer: str = "auto") -> Any:
        _tag_show(self, renderer)

    def __str__(self) -> str:
        return self.get_html_string()

    def __eq__(self, other: Any) -> bool:
        return _equals_impl(self, other)

    def __repr__(self) -> str:
        return self.get_html_string()

    def _repr_html_(self) -> str:
        return self.get_html_string()


# =============================================================================
# TagAttrs class
# =============================================================================
class TagAttrs(Dict[str, str]):
    def __init__(self, **kwargs: TagAttrArg) -> None:
        super().__init__()
        self.update(**kwargs)

    def __setitem__(self, name: str, value: TagAttrArg) -> None:
        val = self._normalize_attr_value(value)
        if val is not None:
            nm = self._normalize_attr_name(name)
            super().__setitem__(nm, val)

    def update(self, **kwargs: TagAttrArg) -> None:
        attrs: Dict[str, str] = {}
        for key, val in kwargs.items():
            val_ = self._normalize_attr_value(val)
            if val_ is None:
                continue
            attrs[self._normalize_attr_name(key)] = val_
        super().update(**attrs)

    @staticmethod
    def _normalize_attr_name(x: str) -> str:
        # e.g., foo_Bar_ -> foo-bar
        if x.endswith("_"):
            x = x[:-1]
        return x.replace("_", "-").lower()

    @staticmethod
    def _normalize_attr_value(x: TagAttrArg) -> Optional[str]:
        if x is None or x is False:
            return None
        if x is True:
            return ""
        if isinstance(x, (int, float)):
            return str(x)
        if isinstance(x, (HTML, str)):
            return x
        raise TypeError(
            f"Invalid type for attribute: {type(x)}."
            + "Consider calling str() on this value before treating it as a tag attribute."
        )


# =============================================================================
# Tag class
# =============================================================================
class Tag:
    """
    Create an HTML tag.

    Methods:
    --------
        show: Preview as a complete HTML document.
        save_html: Save to a HTML file.
        append: Append children to existing children.
        extend: Append an iterable child to existing children.
        insert: Add children into a specific child index.
        add_class: Add a class to the tag.
        has_class: Check if the class attribte contains a particular class.
        render: Returns the HTML string and list of dependencies.
        get_html_string: the HTML string.
        get_dependencies: the HTMLDependency()s.
        tagify: Converts any tagifiable children to Tag/TagList objects.

    Attributes:
    -----------
        name: The name of the tag as a string
        attrs: A dictionary of attributes.
        children: A list of children.

    Examples:
    ---------
        >>> from htmltools import *
        >>> x = div("hello", id="foo", class_="bar")
        >>> x
        >>> print(x)
        >>> x.show()
    """

    def __init__(
        self,
        _name: str,
        *args: TagChildArg,
        children: Optional[List[TagChildArg]] = None,
        **kwargs: TagAttrArg,
    ) -> None:
        self.name: str = _name
        self.attrs: TagAttrs = TagAttrs(**kwargs)
        self.children: TagList = TagList()

        self.children.extend(args)
        if children:
            self.children.extend(children)

    def __call__(self, *args: TagChildArg, **kwargs: TagAttrArg) -> "Tag":
        self.children.extend(args)
        self.attrs.update(**kwargs)
        return self

    def __copy__(self: TagT) -> TagT:
        cls = self.__class__
        cp = cls.__new__(cls)
        # Any instance fields (like .children, and _attrs for the tag subclass) are
        # shallow-copied.
        new_dict = {key: copy(value) for key, value in self.__dict__.items()}
        cp.__dict__.update(new_dict)
        return cp

    def insert(self, index: SupportsIndex, x: TagChildArg) -> None:
        self.children.insert(index, x)

    def extend(self, x: Iterable[TagChildArg]) -> None:
        self.children.extend(x)

    def append(self, *args: TagChildArg) -> None:
        self.children.append(*args)

    def add_class(self, x: str) -> "Tag":
        """
        Add an HTML class attribute.

        Args:
            x: The class name to add.

        Returns: The modified tag.
        """
        cls = self.attrs.get("class")
        if cls:
            x = cls + " " + x
        self.attrs["class"] = x
        return self

    def has_class(self, class_: str) -> bool:
        """
        Check if the tag has a particular class.

        Args:
            class_: The class name to check for.

        Returns: `True` if the tag has the class, `False` otherwise.
        """
        cls = self.attrs.get("class")
        if cls:
            return class_ in cls.split(" ")
        else:
            return False

    def tagify(self: TagT) -> TagT:
        # TODO: Does this result in extra copies of the NodeList?
        cp = copy(self)
        cp.children = cp.children.tagify()
        return cp

    def get_html_string(self, indent: int = 0, eol: str = "\n") -> "HTML":
        indent_str = "  " * indent
        html_ = indent_str + "<" + self.name

        # Write attributes
        for key, val in self.attrs.items():
            if not isinstance(val, HTML):
                val = _html_escape(val, attr=True)
            html_ += f' {key}="{val}"'

        # Dependencies are ignored in the HTML output
        children = [x for x in self.children if not isinstance(x, MetadataNode)]

        # Don't enclose JSX/void elements if there are no children
        if len(children) == 0 and self.name in _VOID_TAG_NAMES:
            return HTML(html_ + "/>")

        # Other empty tags are enclosed
        html_ += ">"
        close = "</" + self.name + ">"
        if len(children) == 0:
            return HTML(html_ + close)

        # Inline a single/empty child text node
        if len(children) == 1 and isinstance(children[0], str):
            return HTML(html_ + _normalize_text(children[0]) + close)

        # Write children
        # TODO: inline elements should eat ws?
        html_ += eol
        html_ += self.children.get_html_string(indent + 1, eol)
        return HTML(html_ + eol + indent_str + close)

    def render(self) -> RenderedHTML:
        cp = self.tagify()
        deps = cp.get_dependencies()
        return {"dependencies": deps, "html": cp.get_html_string()}

    def save_html(self, file: str, lib_prefix: Optional[str] = None) -> str:
        return HTMLDocument(self).save_html(file, lib_prefix)

    def get_dependencies(self, dedup: bool = True) -> List["HTMLDependency"]:
        return self.children.get_dependencies(dedup=dedup)

    def show(self, renderer: str = "auto") -> Any:
        _tag_show(self, renderer)

    def __str__(self) -> str:
        return self.get_html_string()

    def __repr__(self) -> str:
        return self.get_html_string()

    def _repr_html_(self) -> str:
        return self.get_html_string()

    def __eq__(self, other: Any) -> bool:
        return _equals_impl(self, other)


# Tags that have the form <tagname />
_VOID_TAG_NAMES = {
    "area",
    "base",
    "br",
    "col",
    "command",
    "embed",
    "hr",
    "img",
    "input",
    "keygen",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


# =============================================================================
# HTMLDocument class
# =============================================================================
class HTMLDocument:
    """
    Create an HTML document.

    Examples:
    ---------
        >>> print(HTMLDocument(h1("Hello"), tags.meta(name="description", content="test"), lang = "en"))
    """

    def __init__(
        self,
        *args: TagChildArg,
        **kwargs: TagAttrArg,
    ) -> None:
        self._content: TagList = TagList(*args)
        self._html_attr_args: Dict[str, TagAttrArg] = kwargs

    def __copy__(self) -> "HTMLDocument":
        cls = self.__class__
        cp = cls.__new__(cls)
        # Any instance fields (like .children, and _attrs for the tag subclass) are
        # shallow-copied.
        new_dict = {key: copy(value) for key, value in self.__dict__.items()}
        cp.__dict__.update(new_dict)
        return cp

    def append(self, *args: TagChildArg) -> None:
        self._content.append(*args)

    def render(self, *, lib_prefix: Optional[str] = None) -> RenderedHTML:
        html_ = self._gen_html_tag_tree(lib_prefix)
        rendered = html_.render()
        rendered["html"] = "<!DOCTYPE html>\n" + rendered["html"]
        return rendered

    def save_html(self, file: str, lib_prefix: Optional[str] = None) -> str:
        # Directory where dependencies are copied to.
        dest_libdir = str(Path(file).resolve().parent)
        if lib_prefix:
            dest_libdir = os.path.join(dest_libdir, lib_prefix)

        rendered = self.render(lib_prefix=lib_prefix)

        for dep in rendered["dependencies"]:
            dep.copy_to(dest_libdir)

        with open(file, "w") as f:
            f.write(rendered["html"])
        return file

    # Take the stored content, and generate an <html> tag which contains the correct
    # <head> and <body> content. HTMLDependency items will be extracted out of the body
    # and inserted into the <head>.
    # - lib_prefix: A directoy prefix to add to <script src="[lib_prefix]/script.js">
    #   and <link rel="[lib_prefix]/style.css"> tags.
    def _gen_html_tag_tree(self, lib_prefix: Optional[str]) -> Tag:
        content: TagList = self._content
        html: Tag
        body: Tag

        if (
            len(content) == 1
            and isinstance(content[0], Tag)
            and cast(Tag, content[0]).name == "html"
        ):
            html = cast(Tag, content[0])
            html.attrs.update(**self._html_attr_args)
            html = html.tagify()
            html = HTMLDocument._hoist_head_content(html, lib_prefix)
            return html

        if (
            len(content) == 1
            and isinstance(content[0], Tag)
            and cast(Tag, content[0]).name == "body"
        ):
            body = cast(Tag, content[0])
        else:
            body = Tag("body", content)

        body = body.tagify()

        html = Tag("html", Tag("head"), body, **self._html_attr_args)
        html = HTMLDocument._hoist_head_content(html, lib_prefix)
        return html

    # Given an <html> tag object, copies the top node, then extracts dependencies from
    # the tree, and inserts the content from those dependencies into the <head>, such as
    # <link> and <script> tags.
    @staticmethod
    def _hoist_head_content(x: Tag, lib_prefix: Optional[str]) -> Tag:
        if x.name != "html":
            raise ValueError(f"Expected <html> tag, got <{x.name}>.")
        deps: List[HTMLDependency] = x.get_dependencies()
        res = copy(x)
        res.children[0] = copy(res.children[0])
        head = cast(Tag, res.children[0])
        # Put <meta charset="utf-8"> at beginning of head, and other hoisted tags at the
        # end. This matters only if the <head> tag starts out with some children.
        head.insert(0, Tag("meta", charset="utf-8"))
        head.extend([d.as_html_tags(prefix_dir=lib_prefix) for d in deps])
        return res


# =============================================================================
# HTML strings
# =============================================================================
class HTML(str):
    """
    Mark a string as raw HTML.

    Example:
    -------
    >>> print(div("<p>Hello</p>"))
    >>> print(div(HTML("<p>Hello</p>")))
    """

    def __new__(cls, *args: str) -> "HTML":
        return super().__new__(cls, "\n".join(args))

    def __str__(self) -> "HTML":
        return HTML(self)

    # HTML() + HTML() should return HTML()
    def __add__(self, other: Union[str, "HTML"]) -> str:
        res = str.__add__(self, other)
        return HTML(res) if isinstance(other, HTML) else res


# =============================================================================
# HTML dependencies
# =============================================================================
class PackageHTMLDependencySource(TypedDict):
    package: Optional[str]
    subdir: str


class HTMLDependency(MetadataNode):
    """
    Create an HTML dependency.

    Example:
    -------
    >>> dep = HTMLDependency(
            name="mypackage",
            version="1.0",
            source={
                "package": "mypackage",
                "subdir": "lib/",
            },
            script={"src": "foo.js"},
            stylesheet={"href": "css/foo.css"},
        )

    >>> x = div("Hello", dep)
    >>> x.render()
    """

    def __init__(
        self,
        name: str,
        version: Union[str, Version],
        *,
        source: Optional[PackageHTMLDependencySource] = None,
        script: Union[Dict[str, str], List[Dict[str, str]]] = [],
        stylesheet: Union[Dict[str, str], List[Dict[str, str]]] = [],
        all_files: bool = False,
        meta: List[Dict[str, str]] = [],
        head: TagChildArg = None,
    ) -> None:
        self.name: str = name
        self.version: Version = (
            Version(version) if isinstance(version, str) else version
        )
        self.source: Optional[PackageHTMLDependencySource] = source

        if isinstance(script, dict):
            script = [script]
        self._validate_dicts(script, ["src"])
        self.script: List[Dict[str, str]] = script

        if isinstance(stylesheet, dict):
            stylesheet = [stylesheet]
        self._validate_dicts(stylesheet, ["href"])
        self.stylesheet: List[Dict[str, str]] = stylesheet

        # Ensures a rel='stylesheet' default
        for s in self.stylesheet:
            if "rel" not in s:
                s.update({"rel": "stylesheet"})

        self.all_files: bool = all_files
        self.meta: List[Dict[str, str]] = meta
        self.head: Optional[TagChildArg]
        if head is None:
            self.head = None
        else:
            self.head = TagList(head)

    def get_source_dir(self) -> str:
        """Return the directory on disk where the dependency's files reside."""
        if self.source is None:
            return ""
        if self.source["package"] is not None:
            return os.path.join(
                _package_dir(self.source["package"]), self.source["subdir"]
            )
        else:
            return os.path.realpath(self.source["subdir"])

    def as_html_tags(
        self,
        prefix_dir: Optional[str] = None,
    ) -> TagList:
        href_prefix = os.path.join(self.name + "-" + str(self.version))
        if prefix_dir:
            href_prefix = os.path.join(prefix_dir, href_prefix)

        sheets = deepcopy(self.stylesheet)
        for s in sheets:
            s.update(
                {
                    "href": os.path.join(href_prefix, urllib.parse.quote(s["href"])),
                    "rel": "stylesheet",
                }
            )

        script = deepcopy(self.script)
        for s in script:
            s.update({"src": os.path.join(href_prefix, urllib.parse.quote(s["src"]))})

        metas = [Tag("meta", **m) for m in self.meta]
        links = [Tag("link", **s) for s in sheets]
        scripts = [Tag("script", **s) for s in script]
        return TagList(*metas, *links, *scripts, self.head)

    def copy_to(self, path: str) -> None:
        src_file_infos = self._find_src_files()

        # Set up the target directory.
        target_dir = os.path.join(path, self.name + "-" + str(self.version))
        if os.path.exists(target_dir):
            shutil.rmtree(target_dir)
        Path(target_dir).mkdir(parents=True, exist_ok=True)

        # Copy all the files
        for file_info in src_file_infos:
            src_file = file_info["filepath"]
            if not os.path.isfile(src_file):
                raise Exception(
                    f"Failed to copy HTML dependency {self.name}-{str(self.version)} "
                    + f"to {path} because {src_file} doesn't exist."
                )
            target_file = os.path.join(target_dir, path, file_info["href"])
            os.makedirs(os.path.dirname(target_file), exist_ok=True)
            shutil.copy2(src_file, target_file)

    # Returns an object like:
    # [
    #   {
    #     "filepath": "/xyz/htmltools/lib/testdep/testdep.js",
    #     "href": "test-0.0.1/testdep.js"
    #   },
    #   {
    #     "filepath": "/xyz/htmltools/lib/testdep/testdep.css",
    #     "href": "test-0.0.1/testdep.css"
    #   }
    # ]
    def _find_src_files(self) -> List[Dict[str, str]]:
        src_dir: str = self.get_source_dir()
        if src_dir == "":
            return []

        # Collect all the source files
        if self.all_files:
            src_files = list(Path(src_dir).glob("*"))
            src_files = [str(x) for x in src_files]
        else:
            src_files = [
                *[s["src"] for s in self.script],
                *[s["href"] for s in self.stylesheet],
            ]

        # For example: "htmltools-0.0.1"
        dest_href_prefix = os.path.join(self.name + "-" + str(self.version))

        result: List[Dict[str, str]] = []
        for f in src_files:
            src_file_path = os.path.join(src_dir, f)
            if not os.path.isfile(src_file_path):
                raise RuntimeError(
                    f"Failed to find HTML dependency {self.name}-{self.version} "
                    + f"because {src_file_path} doesn't exist."
                )

            result.append(
                {
                    "filepath": src_file_path,
                    "href": os.path.join(dest_href_prefix, f),
                }
            )

        return result

    def _validate_dicts(
        self, ld: List[Dict[str, str]], req_attr: List[str] = []
    ) -> None:
        for d in ld:
            self._validate_dict(d, req_attr)

    def _validate_dict(self, d: object, req_attr: List[str] = []) -> None:
        if not isinstance(d, dict):
            raise TypeError(
                f"Expected dict, got {type(d)} for {d} in HTMLDependency "
                + f"{self.name}-{self.version}"
            )
        for a in req_attr:
            if a not in d:
                raise KeyError(
                    f"Missing required attribute '{a}' for {d} in HTMLDependency "
                    + f"{self.name}-{self.version}"
                )

    def __repr__(self):
        return f'<HTMLDependency "{self.name}-{self.version}">'

    def __str__(self):
        return str(self.as_html_tags())

    def __eq__(self, other: Any) -> bool:
        return _equals_impl(self, other)


def _resolve_dependencies(deps: List[HTMLDependency]) -> List[HTMLDependency]:
    map: Dict[str, HTMLDependency] = {}
    for dep in deps:
        if dep.name not in map:
            map[dep.name] = dep
        else:
            if dep.version > map[dep.name].version:
                map[dep.name] = dep

    return list(map.values())


def head_content(*args: TagChildArg) -> HTMLDependency:
    head = TagList(*args)
    head_str = head.get_html_string()
    # Create unique ID to use as name
    name = "headcontent_{:x}".format(abs(hash(head_str)))
    return HTMLDependency(name=name, version="0.0", head=head)


# =============================================================================
# Utility functions
# =============================================================================

# Convert a list of TagChildArg objects to a list of TagChild objects. Does not alter
# input object.
def _tagchildargs_to_tagchilds(x: Iterable[TagChildArg]) -> List[TagChild]:
    result = _flatten(x)
    for i, child in enumerate(result):
        if isinstance(child, (int, float)):
            result[i] = str(child)
        elif not isinstance(child, (Tagifiable, Tag, MetadataNode, str)):
            raise TypeError(
                f"Invalid tag child type: {type(child)}. "
                + "Consider calling str() on this value before treating it as a tag child."
            )

    # At this point, we know that all items in new_children must be valid TagChild
    # objects, because None, int, float, and TagList objects have been removed. (Note
    # that the TagList objects that have been flattened are TagList which are NOT
    # tags.)
    return cast(List[TagChild], result)


# Walk a Tag tree, and apply a function to each node. The node in the tree will be
# replaced with the value returned from `fn()`. If the function alters a node, then it
# will be reflected in the original object that `.walk_mutate()` was called on.
#
# Note that if we were to export this function (perhaps in a class method), some other
# possible variants are:
# * Instead of one `fn`, take `pre` and `post` functions.
# * Allow functions that return `TagChildArg`, and then flatten/convert those to
#   `TagChild`.
# * Provide a `_walk` function that doesn't mutate the tree. It would return `None`, and
#   `fn` should return `None`. This could be useful when `fn` just collects things from
#   the tree.
def _walk_mutate(x: TagChild, fn: Callable[[TagChild], TagChild]) -> TagChild:
    x = fn(x)
    if isinstance(x, Tag):
        for i, child in enumerate(x.children):
            x.children[i] = _walk_mutate(child, fn)
    return x


def _tag_show(self: Union[TagList, "Tag"], renderer: str = "auto") -> Any:
    if renderer == "auto":
        try:
            import IPython

            ipy = IPython.get_ipython()  # type: ignore
            renderer = "ipython" if ipy else "browser"
        except ImportError:
            renderer = "browser"

    # TODO: can we get htmlDependencies working in IPython?
    if renderer == "ipython":
        from IPython.core.display import display_html

        # https://github.com/ipython/ipython/pull/10962
        return display_html(
            str(self), raw=True, metadata={"text/html": {"isolated": True}}
        )  # type: ignore

    if renderer == "browser":
        tmpdir = tempfile.gettempdir()
        key_ = "viewhtml" + str(hash(str(self)))
        dir = os.path.join(tmpdir, key_)
        Path(dir).mkdir(parents=True, exist_ok=True)
        file = os.path.join(dir, "index.html")
        self.save_html(file)
        port = ensure_http_server(tmpdir)
        webbrowser.open(f"http://localhost:{port}/{key_}/index.html")
        return file

    raise Exception(f"Unknown renderer {renderer}")


def _normalize_text(txt: str) -> str:
    if isinstance(txt, HTML):
        return txt
    else:
        return _html_escape(txt, attr=False)


def _equals_impl(x: Any, y: Any) -> bool:
    if not isinstance(y, type(x)):
        return False
    for key in x.__dict__.keys():
        if getattr(x, key, None) != getattr(y, key, None):
            return False
    return True
