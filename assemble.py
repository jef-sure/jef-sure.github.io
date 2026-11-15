#!/usr/bin/env python3
"""Put the documentation of several repositories into one MkDocs tree.

The nav of mkdocs.yml names the pages, projects.yml says which repository
each section comes from, and each repository is taken at its latest release
tag. The links of the pages are rewritten: a link to a page that is on the
site leads to that page, a link to any other file of the repository leads to
the file on GitHub at the same tag, and the pictures the pages show are
copied next to them. Nothing else of a repository reaches the site.

    assemble.py                       the repositories from GitHub
    assemble.py --from ~/git          local clones, at their latest tags
    assemble.py --from ~/git --worktree
                                      local working trees as they are, to
                                      look at pages before a release
"""

import argparse
import os
import posixpath
import re
import shutil
import subprocess
import sys
from urllib.parse import quote, unquote

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
DOCS = os.path.join(BUILD, "docs")
SRC = os.path.join(BUILD, "src")
PAGES = os.path.join(HERE, "pages")  # the pages of the site itself


class Loader(yaml.SafeLoader):
    """Reads mkdocs.yml without building the Python objects it names."""


Loader.add_multi_constructor("tag:yaml.org,2002:python/", lambda *a: None)
Loader.add_multi_constructor("!", lambda *a: None)


def git(*args, cwd=None):
    return subprocess.run(["git", "-c", "advice.detachedHead=false", *args], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout


VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def latest_tag(url):
    tags = []
    for line in git("ls-remote", "--tags", "--refs", url).splitlines():
        name = line.split("refs/tags/", 1)[1]
        m = VERSION.match(name)
        if m:
            tags.append((tuple(map(int, m.groups())), name))
    if not tags:
        sys.exit(f"{url}: no tag of a release (like 1.2.3 or v1.2.3)")
    return max(tags)[1]


def nav_pages(items):
    for item in items:
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            for value in item.values():
                if isinstance(value, str):
                    yield value
                elif isinstance(value, list):
                    yield from nav_pages(value)


def repo_path_of(rel, overrides):
    """The file of the repository a page of a section is made from."""
    if rel in overrides:
        return overrides[rel]
    if rel == "index.md":
        return "README.md"
    if rel.endswith("/index.md"):
        return rel[: -len("index.md")] + "README.md"
    return "docs/" + rel


def site_path_of_file(path):
    """Where a picture of the repository goes in its section."""
    return path[len("docs/"):] if path.startswith("docs/") else path


class Project:
    def __init__(self, section, repo, overrides):
        self.section = section
        self.repo = repo
        self.overrides = overrides
        self.dir = None
        self.ref = None
        self.pages = {}  # path in the repository -> path on the site


GH = re.compile(r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<kind>blob|tree|raw)/"
                r"(?P<ref>[^/]+)/?(?P<path>[^?#]*)(?P<rest>[?#].*)?$")
RAW = re.compile(r"^https?://raw\.githubusercontent\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/"
                 r"(?P<ref>[^/]+)/(?P<path>[^?#]*)(?P<rest>[?#].*)?$")
SCHEME = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//)")

# a code span is matched first and given back as it is, so a link inside it is
# left alone, while a link whose text holds a code span is still a link
INLINE = re.compile(r"""
    (?P<code>(?P<ticks>`+).+?(?P=ticks))
  | (?P<bang>!?)\[(?P<text>(?:[^\[\]`]|`[^`]*`|\[[^\[\]]*\])*)\]
    \((?P<sp>[ \t]*)(?P<url><[^>\n]*>|[^\s()]*(?:\([^\s()]*\)[^\s()]*)*)
    (?P<title>[ \t]+(?:"[^"]*"|'[^']*'))?[ \t]*\)
  | (?P<attr>\b(?:href|src|srcset)=)(?P<q>["'])(?P<aurl>.*?)(?P=q)
""", re.X)
CODE_SPAN = re.compile(r"(`+)[^\n]+?\1")
DETAILS = re.compile(r"^ {0,3}<details(?![^>]*\bmarkdown\b)")
REFDEF = re.compile(r"^(?P<pre> {0,3}\[[^\]]+\]:[ \t]*)(?P<url><[^>]*>|\S+)(?P<rest>.*)$")
FENCE = re.compile(r"^[ \t]*(?P<f>`{3,}|~{3,})")


class Site:
    def __init__(self, owner, projects):
        self.owner = owner
        self.projects = projects  # section -> Project
        self.by_repo = {p.repo.lower(): p for p in projects.values()}
        self.problems = []

    # -- links ---------------------------------------------------------------

    def resolve(self, url, page, image):
        if not url or url.startswith("#"):
            return url
        m = GH.match(url) or RAW.match(url)
        if m:
            project = self.by_repo.get(m["repo"].lower())
            if m["owner"].lower() != self.owner.lower() or project is None:
                return url
            path = unquote(m["path"]).strip("/")
            rest = m["rest"] or ""
            if m.re is RAW or m["kind"] == "raw":
                image = True
        elif SCHEME.match(url):
            return url
        elif url.startswith("/"):
            self.problems.append(f"{page.site}: absolute path {url}")
            return url
        else:
            cut = min([i for i in (url.find("#"), url.find("?")) if i >= 0] or [len(url)])
            here = posixpath.dirname(page.repo_path)
            path = posixpath.normpath(posixpath.join(here, unquote(url[:cut])))
            rest = url[cut:]
            if path == "..." or path.startswith("../") or path == "..":
                self.problems.append(f"{page.site}: {url} leads out of the repository")
                return url
            path = "" if path == "." else path
            project = page.project
        return self.target(project, path, rest, page, image)

    def target(self, project, path, rest, page, image):
        frag = rest
        if frag.startswith("#"):
            frag = "#" + unquote(frag[1:])
        for candidate in (path, posixpath.join(path, "README.md") if path else "README.md"):
            if candidate in project.pages:
                return self.relative(project.pages[candidate], page.site) + frag
        full = os.path.join(project.dir, path)
        if image and os.path.isfile(full):
            site = project.section + "/" + site_path_of_file(path)
            dest = os.path.join(DOCS, site)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(full, dest)
            return self.relative(site, page.site)
        if os.path.isdir(full):
            kind = "tree"
        else:
            kind = "blob"
            if not os.path.isfile(full):
                self.problems.append(f"{page.site}: {path or '/'} is not in {project.repo} at {project.ref}")
        return f"https://github.com/{self.owner}/{project.repo}/{kind}/{project.ref}/{quote(path)}{rest}"

    @staticmethod
    def relative(target, source):
        return posixpath.relpath(target, posixpath.dirname(source))

    # -- pages ---------------------------------------------------------------

    def rewrite_inline(self, text, page):
        def one(m):
            if m["code"]:
                return m[0]
            if m["attr"]:
                value = m["aurl"]
                if m["attr"].startswith("srcset"):
                    parts = []
                    for item in value.split(","):
                        bits = item.strip().split(None, 1)
                        bits[0] = self.resolve(bits[0], page, True)
                        parts.append(" ".join(bits))
                    value = ", ".join(parts)
                else:
                    value = self.resolve(value, page, m["attr"].startswith("src"))
                return f'{m["attr"]}{m["q"]}{value}{m["q"]}'
            url = m["url"]
            bracketed = url.startswith("<")
            if bracketed:
                url = url[1:-1]
            url = self.resolve(url, page, bool(m["bang"]))
            if bracketed:
                url = f"<{url}>"
            text = self.rewrite_inline(m["text"], page)  # a picture inside a link
            return f'{m["bang"]}[{text}]({m["sp"]}{url}{m["title"] or ""})'
        return INLINE.sub(one, text)

    def rewrite(self, text, page):
        lines = relist(text.split("\n"))
        out = []
        para = []

        def flush():
            if para:
                out.append(self.rewrite_inline("\n".join(para), page))
                para.clear()

        for line, code in lines:
            if code or not line.strip():
                flush()
                out.append(line)
                continue
            r = REFDEF.match(line)
            if r:
                flush()
                url = r["url"]
                bracketed = url.startswith("<")
                url = self.resolve(url[1:-1] if bracketed else url, page, False)
                out.append(r["pre"] + (f"<{url}>" if bracketed else url) + r["rest"])
                continue
            if DETAILS.match(line):
                # GitHub reads Markdown inside <details>; Python-Markdown
                # (md_in_html) does so only when the tag asks for it
                line = DETAILS.sub(r"\g<0> markdown", line, count=1)
            if line.lstrip().startswith("|"):
                # in a table GitHub needs \| for a | inside code and shows it
                # as |; Python-Markdown does not split cells inside code and
                # would show the backslash
                line = CODE_SPAN.sub(lambda c: c[0].replace("\\|", "|"), line)
            para.append(line)
        flush()
        return "\n".join(out)


def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def closes(line, fence):
    m = FENCE.match(line)
    return bool(m) and m["f"][0] == fence[0] and len(m["f"]) >= len(fence) \
        and not line.strip()[len(m["f"]):].strip()


ITEM = re.compile(r"^(?P<ind> *)(?P<mark>[-*+]|\d{1,9}[.)])(?P<sp> +|$)")


class Level:
    def __init__(self, marker, content, depth):
        self.marker = marker      # where the marker stands in the source
        self.content = content    # where the text of the item starts in the source
        self.new = 4 * depth + 4  # where the text starts for Python-Markdown


QUOTE = re.compile(r"^ {0,3}> ?")


def relist(lines):
    """Lists as GitHub reads them, indented as Python-Markdown wants them.

    GitHub nests a list, a paragraph or a fenced block under an item by the
    column where the text of the item starts, two spaces after "- ";
    Python-Markdown wants four for each level. Lines that belong to an item
    are moved to its column of four; the lines of a fenced block keep their
    indentation inside the block, tabs included. GitHub also lets an item
    follow a paragraph with no blank line between, while Python-Markdown then
    takes the item for a part of the paragraph or of the item before, so a
    blank line is put there. The text of a quote is treated the same way.
    Returns pairs (line, is code).
    """
    out = []
    stack = []
    fence = None  # (fence, source column to strip, new column)
    prev_blank = True
    prev_text = ""
    block_is_item = False  # the block since the last blank line began with an item
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if fence:
            f, strip, new = fence
            if closes(raw, f):
                fence = None
            cut = min(strip, indent_of(raw))
            out.append(((" " * new + raw[cut:]) if raw.strip() else "", True))
            continue
        line = raw.expandtabs(4)
        if not line.strip():
            out.append(("", False))
            prev_blank = True
            continue
        if not stack and QUOTE.match(line):
            quote = [line]
            while i < len(lines) and QUOTE.match(lines[i]):
                quote.append(lines[i])
                i += 1
            for text, code in relist([QUOTE.sub("", q, count=1) for q in quote]):
                out.append(("> " + text if text else ">", code))
            prev_blank = False
            prev_text = ">"
            block_is_item = False
            continue
        ind = indent_of(line)
        m = ITEM.match(line)
        if m and not prev_blank:
            mark = m["mark"]
            if prev_text.startswith("<"):
                m = None  # the line belongs to a block of HTML
            elif not stack and not (mark in "-*+" or mark[:-1] == "1"):
                m = None  # GitHub starts a list in a paragraph only with a bullet or "1."
        if m and ind < (stack[-1].content if stack else 0) + 4:
            if not prev_blank and not block_is_item:
                out.append(("", False))
            block_is_item = True
            while stack and stack[-1].content > ind:
                stack.pop()
            level = Level(ind, ind + len(m["mark"]) + max(1, len(m["sp"])), len(stack))
            stack.append(level)
            new_line = " " * (level.new - 4) + line[ind:]
        else:
            if prev_blank:
                block_is_item = False
            if stack and ind >= stack[-1].content:
                new_line = " " * stack[-1].new + line[stack[-1].content:]
            elif stack and not prev_blank:
                new_line = " " * stack[-1].new + line.lstrip(" ")  # a lazy line of the paragraph
            else:
                while stack and stack[-1].content > ind:
                    stack.pop()
                new_line = (" " * stack[-1].new + line[stack[-1].content:]) if stack else line
        f = FENCE.match(new_line)
        if f and (stack or ind < 4):
            fence = (f["f"], ind, indent_of(new_line))
            out.append((new_line, True))
        else:
            out.append((new_line, False))
        prev_blank = False
        prev_text = line.lstrip(" ")
    return out


def check_fences(text, where, problems):
    """A fence without its pair turns the rest of the page into code or code
    into text, and MkDocs does not notice. An opening fence with a language
    inside a block that is already open is the usual sign of one."""
    fence = None
    for n, line in enumerate(text.split("\n"), 1):
        m = FENCE.match(line)
        if not m:
            continue
        if fence is None:
            fence = (m["f"], n)
        elif closes(line, fence[0]):
            fence = None
        elif line.strip()[len(m["f"]):].strip():
            problems.append(f"{where}: line {n} opens a code block inside the one of line {fence[1]}")
    if fence:
        problems.append(f"{where}: the code fence of line {fence[1]} is never closed")


class Page:
    def __init__(self, project, repo_path, site):
        self.project = project
        self.repo_path = repo_path
        self.site = site


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="local", metavar="DIR",
                    help="take the repositories from local clones in DIR, named as on GitHub")
    ap.add_argument("--worktree", action="store_true",
                    help="with --from: the files as they lie, committed or not")
    ap.add_argument("--strict", action="store_true", help="stop on a link that leads nowhere")
    args = ap.parse_args()
    if args.worktree and not args.local:
        ap.error("--worktree needs --from")

    with open(os.path.join(HERE, "projects.yml")) as f:
        conf = yaml.safe_load(f)
    with open(os.path.join(HERE, "mkdocs.yml")) as f:
        mkdocs = yaml.load(f, Loader=Loader)

    owner = conf["owner"]
    projects = {s: Project(s, p["repo"], p.get("pages") or {}) for s, p in conf["projects"].items()}
    site = Site(owner, projects)

    shutil.rmtree(DOCS, ignore_errors=True)
    os.makedirs(SRC, exist_ok=True)

    for project in projects.values():
        if args.worktree:
            project.dir = os.path.join(os.path.expanduser(args.local), project.repo)
            project.ref = git("rev-parse", "--abbrev-ref", "HEAD", cwd=project.dir).strip()
            print(f"{project.section}: {project.dir}, working tree on {project.ref}")
            continue
        if args.local:
            url = "file://" + os.path.join(os.path.abspath(os.path.expanduser(args.local)), project.repo)
        else:
            url = f"https://github.com/{owner}/{project.repo}.git"
        project.ref = latest_tag(url)
        project.dir = os.path.join(SRC, project.section)
        shutil.rmtree(project.dir, ignore_errors=True)
        git("clone", "--quiet", "--depth", "1", "--branch", project.ref, url, project.dir)
        print(f"{project.section}: {project.repo} at {project.ref}")

    # the pictures and styles of the site's own pages go as they are; its
    # pages of Markdown, like those of the repositories, only by the nav
    for root, _, names in os.walk(PAGES):
        for name in names:
            if name.endswith(".md"):
                continue
            src = os.path.join(root, name)
            dest = os.path.join(DOCS, os.path.relpath(src, PAGES))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(src, dest)

    pages = []
    for site_path in nav_pages(mkdocs["nav"]):
        section, _, rel = site_path.partition("/")
        if section not in projects:
            src = os.path.join(PAGES, site_path)
            if not os.path.isfile(src):
                sys.exit(f"{site_path}: the nav names it, but pages/ has no such file")
            dest = os.path.join(DOCS, site_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(src, dest)
            with open(src, encoding="utf-8") as f:
                check_fences(f.read(), site_path, site.problems)
            continue
        project = projects[section]
        repo_path = repo_path_of(rel, project.overrides)
        if not os.path.isfile(os.path.join(project.dir, repo_path)):
            sys.exit(f"{site_path}: {project.repo} has no {repo_path} at {project.ref}")
        project.pages[repo_path] = site_path
        pages.append(Page(project, repo_path, site_path))

    for page in pages:
        with open(os.path.join(page.project.dir, page.repo_path), encoding="utf-8") as f:
            text = f.read()
        dest = os.path.join(DOCS, page.site)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(site.rewrite(text, page))
        check_fences(text, page.site, site.problems)

    for problem in site.problems:
        print("warning:", problem, file=sys.stderr)
    print(f"{len(pages)} pages in {DOCS}")
    if args.strict and site.problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
