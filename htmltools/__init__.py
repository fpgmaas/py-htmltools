__version__ = "0.1.0.9001"

from ._core import (
    TagList,
    Tag,
    HTMLDocument,
    HTML,
    MetadataNode,
    HTMLDependency,
    RenderedHTML,
    TagAttrArg,
    TagChildArg,
    TagChild,
    TagFunction,
    Tagifiable,
    head_content,
)
from ._jsx import jsx, jsx_tag_create, JSXTag, JSXTagAttrArg
from ._util import css
from .tags import (
    p,
    h1,
    h2,
    h3,
    h4,
    h5,
    h6,
    a,
    br,
    div,
    span,
    pre,
    code,
    img,
    strong,
    em,
    hr,
)
from . import tags
from . import svg

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
    "Tagifiable",
    "head_content",
    "jsx",
    "jsx_tag_create",
    "JSXTag",
    "JSXTagAttrArg",
    "css",
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "a",
    "br",
    "div",
    "span",
    "pre",
    "code",
    "img",
    "strong",
    "em",
    "hr",
    "tags",
    "svg",
)
