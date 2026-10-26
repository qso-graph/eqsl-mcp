# Changelog

All notable changes to `eqsl-mcp` are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `--version` and `--help` now print and exit. They were ignored, so the
  command started the MCP server on stdio and waited for JSON-RPC — leaving a
  FastMCP banner on screen and an apparently hung terminal. Seven servers in
  this fleet already behaved correctly; this brings the rest in line, and a
  test asserts it.

## [0.4.1] — 2026-10-26

- A release should appear on the Releases page
- Move every Node 20 action to its first Node 24 major
- The locked-dependency audit blocked every release
- Four upgrades arrived as 57 pull requests
- Nothing was auditing the lockfile
- Close every open security advisory in the lockfile
- A release is a workflow, not a merge
- Make the publish gate's http:// check portable
- Assert that certifi is declared, not merely imported

## [0.4.0] — 2026-10-12

**Upgrading:** a credential failure now returns `isError: true` instead of a successful result whose
payload contained an `error` key. Anything reading `result["error"]` should read the error flag.
Other failures — a network error, eQSL refusing — already reached a client as errors and are
unchanged.

**Security-relevant:** eQSL's own response body was returned as the error text, and this server's
requests put the password in the query string. A body echoing the request used to carry the
password into the message. That text is now withheld, with a reason, when it contains the secret or
any URL.


- **`E501` is adopted** (#22, qso-graph-devel#70). It reported **nothing** — this source was
  already within 95 columns, so adoption was the config change alone with no reflow, and the repo
  carries no `noqa`. That the rule is enforced rather than inert was checked rather than assumed: a
  planted 117-character line is reported, and removed again the tree is clean.

- **`certifi` is carried, and both fetch paths verify against it** (#21, qso-graph-devel#73). They
  used `urllib` with no context, so they trusted whichever root store the running Python was built
  against. On macOS that is `/etc/ssl/cert.pem`, a deliberately *reduced* OpenSSL file — 128 roots
  against the system keychain's 158, and current rather than stale. **eqsl.cc verifies fine against
  it today**, so this was latent rather than an outage.
- **It matters most on the credentialed path:** eQSL's query interface puts the operator's password
  in the query string, so `ssl.CERT_NONE` there would mean handing the password to whoever
  presented a certificate. That is why verification is never disabled, rather than merely why it
  should not be.
- The context lives in its own module, `_tls.py`, because the calls are in two files — `client.py`
  and `ag_cache.py` — and the "every `urlopen` verifies" check scans the whole package. A check
  reading one file would have left the other unverified, and which one is worse depends only on
  which file it happened to read.
- **`tests/test_release_gate.py`** asserts the gate suite imports nothing but the standard library
  and pytest. solar-mcp's 0.3.0 publish failed on exactly that, from the same change.

- **Credential failures are flagged `isError`** (#23). Three tools caught `CredentialError` and
  returned `{"error": "..."}`, which reaches a client as a *successful* call whose payload happens
  to contain the word "error". They now raise `ToolError`. **No decision changed — only how it is
  reported.**
- **Measured while doing it: this server was already half-right, by accident.** Its tools caught
  *only* `CredentialError`, so every other failure — a network error, eQSL refusing — propagated
  uncaught, and `fastmcp` already reported those as `isError` with the message intact. That
  behaviour was being relied on with nothing asserting it, so a later tidy-up adding a blanket
  `except Exception: return {...}` would have silently undone it. It is now pinned by a test, which
  also refuses any `{"error": ...}` return creeping back into `server.py`.
- **Fixed: eQSL's own response body could carry the password into the message.** `last_upload_date`
  stripped the tags off whatever eQSL returned and handed that back, and this server's requests put
  the password in the query string. **Measured, not assumed:** given a body echoing the request the
  secret came straight through. That text is now withheld, with a reason, when it carries the
  secret or anything URL-shaped, and capped — while an ordinary `Invalid user name` still reaches
  the caller. Same shape as the fix in `lotw-mcp`.
- **Every tool declares all four annotation hints** (#23). All six are read-only, non-destructive
  and idempotent; `openWorldHint` is true for the five that reach eqsl.cc — three with the
  operator's credentials, two on public endpoints — and false for `get_version_info`.
- **`tests/test_mcp_conformance.py`** asserts all of the above.

## [0.3.8] — 2026-10-11

- **ruff and mypy run in CI** (qso-graph-devel#66), as a job the `ci-all-green` gate requires.
  Settings follow `adif-mcp`, the reference for every qso-graph Python repo, rather than a style of
  this repo's own. They run once rather than per Python version: both read the source, and neither
  answer changes with the interpreter.
- Five tool functions were annotated `-> dict` with no type arguments, so nothing checked what
  they return. They say `dict[str, Any]` now.
- `E501` is deferred rather than adopted (qso-graph-devel#70): what it reports in these repos are
  widths, not defects, and some lines are long because they name a publisher's field exactly.
- `mcp.run` is given the literal fastmcp asks for rather than a `str` that happens to hold the
  right word.
- **`fastmcp` is bounded: `>=4.0,<5`** (qso-graph-devel#60). It was `>=3.0` with no upper bound, and
  these servers are run with `uvx`, which resolves fresh — so a `fastmcp` 5.0 would have reached
  every user automatically, before anything here had been run against it. The floor rises to 4.0
  because that is what is actually tested: every lock in the fleet held a 4.x, and nothing in CI
  has ever exercised 3.x. A claim of 3.x support that no test backs is not support.
- `fastmcp` is locked at 4.1.0, the current release, so CI runs against what a new install gets.
- **The published contact is `maintainers@qso-graph.io`** (qso-graph-devel#69). The `authors` field
  carried a personal address, and that field is what PyPI shows on the package page. Everything in
  qso-graph is open source and open to contribution, so the contact is the project's.

## [0.3.7] — 2026-10-07

- LICENSE: the full GPL-3.0 text. The file held only its opening and a link, so GitHub detected no licence.

## [0.3.6] — 2026-10-06

- PyPI: the Documentation link goes to this package's own page, https://qso-graph.io/servers/eqsl/ (qso-graph/.github#15).
- CI: the release flow (qso-graph/.github TEMPLATES.md). Work lands on `develop`; a release is a
  PR from `develop` into `main`, and merging it publishes to PyPI and the MCP Registry, verifies both
  and tags the release. CI runs on `develop` too, and PRs into `main` must come from `develop` or a
  `security/` branch.

## [0.3.5] — 2026-10-04

Documentation only; no code changes. Released so the PyPI page shows the corrected README.

### Changed
- README: the credential steps used `qso-auth persona create / provider / secret`, which don't exist. Now `persona add`, `provider enable`, `creds set` (#6).
- README: `eqsl_download` returns your inbox as ADIF, not card images; Known Quirks for the AG cache and the inbox download (#6).
- README: uvx only, no pip (#5).

## [0.3.4] — 2026-09-28

### Added (CI hygiene)

- **MCP Registry sync** — `publish.yml` publishes to the [Official MCP Registry](https://registry.modelcontextprotocol.io)
  after each PyPI publish, using GitHub OIDC for auth. Triggered on
  `v*` tag push; no manual steps. The Registry job waits until PyPI
  serves the version, and retries. Pattern documented in
  [qso-graph/.github/TEMPLATES.md](https://github.com/qso-graph/.github/blob/main/TEMPLATES.md).
- **Registry version badge** in README — PyPI and Registry versions
  are visible side-by-side so any drift between publishing surfaces
  is immediately apparent.
- **Release gates** — the tag must match `pyproject.toml`, and a
  `verify` job fails the release unless PyPI and the MCP Registry
  both serve the new version.

### Fixed

- The Official MCP Registry listed eqsl-mcp at 0.2.0. This release brings it current.

## [0.3.3] — 2026-05-16

### Added
- New tool `get_version_info` — returns `{service_name, service_version, spec_version}`
  for fleet identity attestation. Tracks [IONIS-AI/ionis-devel#49](https://github.com/IONIS-AI/ionis-devel/issues/49).
- `__spec_version__` pinned to `eqsl-cc-v1`.
- L2 unit tests EQSL-L2-046 through EQSL-L2-050.
- `.github/workflows/ci.yml` — PR-gating CI (py3.10-3.13 matrix).

### Changed
- `__init__.py` modernized to fleet pattern (`Final` types).

## [0.3.2] — Previous release
- See git history for changes prior to the changelog being introduced.
