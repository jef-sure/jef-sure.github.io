# The site of my projects

The source of https://jef-sure.github.io/. The documentation of each project
is not written here: it is taken from the project's repository at its latest
release. What lives here, in `pages/`, is the rest:

- the start page and the first page of each tab;
- the articles, moved here from Habr, Hackster and Hackaday.io with their
  pictures, each in English and in Russian;
- About.

- `mkdocs.yml`: the look, and the nav, which is also the list of what each
  section takes. A page that is not in the nav is not on the site.
- `projects.yml`: which repository each section comes from, and how a page of
  the nav is found in it.
- `assemble.py`: takes the repositories, puts the pages of the nav into
  `build/docs` and rewrites their links. A link to a page that is on the site
  leads to that page; a link to any other file leads to it on GitHub at the
  same tag; the pictures the pages show are copied. Lists are re-indented the
  way MkDocs reads them, since GitHub nests by two spaces and MkDocs by four.
- `compare.py`: counts headings, list items, code, table cells and pictures
  of each page against the same file rendered as GitHub reads Markdown. A
  difference means the site shows the file otherwise than GitHub does.

## Building it locally

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python assemble.py                         # from GitHub, latest tags
.venv/bin/python assemble.py --from ~/git            # local clones, latest tags
.venv/bin/python assemble.py --from ~/git --worktree # local files as they are
.venv/bin/mkdocs build --strict && .venv/bin/python compare.py
.venv/bin/python -m http.server -d build/site 8000
```

`mkdocs build --strict` stops on a link to a page that is not on the site and
on an anchor that no heading has.

## Publishing

`.github/workflows/pages.yml` builds and publishes on a push, by hand
(`gh workflow run pages.yml`) and once a day, so a new release of a project
reaches the site by the next morning. The repository's Pages setting must have
"GitHub Actions" as the source.
