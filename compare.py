#!/usr/bin/env python3
"""Compare each page of the site with the same file as GitHub reads it.

The source of a page is rendered by markdown-it (CommonMark with tables, the
way GitHub reads Markdown), the page of the site is taken from build/site,
and the elements of both are counted: headings, lists and their items, code
blocks, tables and their cells, quotes, pictures. A difference means MkDocs
read the file otherwise than GitHub does.
"""

import os
import sys
from collections import Counter
from html.parser import HTMLParser

import yaml
from markdown_it import MarkdownIt

import assemble

TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "pre", "table", "th", "td",
        "blockquote", "img", "hr", "a", "code", "strong", "em", "del", "p"}


class Count(HTMLParser):
    def __init__(self, inside=None):
        super().__init__(convert_charrefs=True)
        self.inside = inside  # count only within <article> when given
        self.depth = 0 if inside else 1
        self.counts = Counter()

    def handle_starttag(self, tag, attrs):
        if self.inside and tag == "article":
            self.depth += 1
        if self.depth and tag in TAGS:
            if tag == "a" and ("class", "headerlink") in attrs:
                return  # the mark of a heading MkDocs adds
            self.counts[tag] += 1

    def handle_endtag(self, tag):
        if self.inside and tag == "article":
            self.depth -= 1


def count(html, inside=None):
    c = Count(inside)
    c.feed(html)
    return c.counts


def main():
    md = MarkdownIt("commonmark").enable("table").enable("strikethrough")
    with open(os.path.join(assemble.HERE, "projects.yml")) as f:
        conf = yaml.safe_load(f)
    with open(os.path.join(assemble.HERE, "mkdocs.yml")) as f:
        nav = yaml.load(f, Loader=assemble.Loader)["nav"]
    bad = 0
    for site_path in assemble.nav_pages(nav):
        section, _, rel = site_path.partition("/")
        if section not in conf["projects"]:
            continue
        repo_path = assemble.repo_path_of(rel, conf["projects"][section].get("pages") or {})
        with open(os.path.join(assemble.SRC, section, repo_path), encoding="utf-8") as f:
            want = count(md.render(f.read()))
        html_path = site_path[:-3] + "/index.html"
        if html_path.endswith("/index/index.html"):
            html_path = html_path[: -len("index/index.html")] + "index.html"
        with open(os.path.join(assemble.BUILD, "site", html_path), encoding="utf-8") as f:
            got = count(f.read(), inside="article")
        diff = {t: (want[t], got[t]) for t in sorted(TAGS) if want[t] != got[t]}
        if diff:
            bad += 1
            print(f"{site_path}: " + ", ".join(f"{t} {w}->{g}" for t, (w, g) in diff.items()))
    print(f"{bad} pages differ")


if __name__ == "__main__":
    main()
