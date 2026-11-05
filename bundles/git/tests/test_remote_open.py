"""tn git remote add / remote ls / open (docs/tn.md §7.5)."""

from __future__ import annotations

from unittest import mock

from tn.plugins import git as gitplugin  # noqa: E402 - tn/plugins/__init__.py maps TN_PLUGIN_PATH

from _gitbase import GitCase


class RemoteAdd(GitCase):
    def setUp(self):
        super().setUp()
        self.r = self.repo("shop-web")

    def test_forge_path_from_context(self):
        r = self.ok(self.tn("git", "remote", "add", "work", "--no-fetch", "--json", cwd=self.r))
        self.assertEqual(r.json, {"name": "gitlab", "url": "git@gitlab.example.com:acme/shop-web.git",
                                  "forge": "work", "path": "acme/shop-web", "fetched": False})
        self.assertEqual(self.local_config(self.r, "remote.gitlab.url"),
                         "git@gitlab.example.com:acme/shop-web.git")

    def test_project_group_and_owner(self):
        self.project_toml("acme", 'group = "acme/web"\n')
        r = self.ok(self.tn("git", "remote", "add", "work", "--no-fetch", "--json", cwd=self.r))
        self.assertEqual(r.json["path"], "acme/web/shop-web")
        r = self.ok(self.tn("git", "remote", "add", "bitbucket", "--no-fetch", "--json",
                            cwd=self.r))
        self.assertEqual(r.json["url"], "git@bitbucket.org:alex/acme-shop-web.git")

    def test_name_and_path(self):
        r = self.ok(self.tn("git", "remote", "add", "gh", "--name", "origin", "--path",
                            "someone/x", "--no-fetch", "--json", cwd=self.r))
        self.assertEqual((r.json["name"], r.json["url"]), ("origin", "git@github.com:someone/x.git"))

    def test_same_url_is_no_change_other_url_fails(self):
        self.ok(self.tn("git", "remote", "add", "gh", "--no-fetch", cwd=self.r))
        self.ok(self.tn("git", "remote", "add", "gh", "--no-fetch", cwd=self.r))
        self.assertExit(self.tn("git", "remote", "add", "gh", "--path", "a/b", "--no-fetch",
                                cwd=self.r), 1)

    def test_failed_fetch_is_a_warning(self):
        r = self.ok(self.tn("git", "remote", "add", "gh", "--json", cwd=self.r))
        self.assertFalse(r.json["fetched"])
        self.assertIn("create it: https://github.com/alex/shop-web (gh repo create", r.stderr)

    def test_unknown_forge(self):
        r = self.tn("git", "remote", "add", "nope", "--json", cwd=self.r)
        self.assertExit(r, 2)
        self.assertEqual(r.error["choices"], ["bitbucket", "gh", "work"])

    def test_outside_a_project_needs_path(self):
        d = self.make_repo(self.home / "loose")
        self.assertExit(self.tn("git", "remote", "add", "gh", "--no-fetch", cwd=d), 2)
        self.ok(self.tn("git", "remote", "add", "gh", "--path", "me/loose", "--no-fetch", cwd=d))

    def test_dry_run(self):
        r = self.ok(self.tn("git", "remote", "add", "gh", "-n", "--json", cwd=self.r))
        self.assertTrue(r.json["dry_run"])
        self.assertEqual(self.git(self.r, "remote").strip(), "")


class RemoteLs(GitCase):
    def test_rows(self):
        r = self.repo("shop-web")
        self.git(r, "remote", "add", "gitlab", "git@gitlab.example.com:acme/shop-web.git")
        self.git(r, "remote", "add", "other", "https://code.example.org/x/y.git")
        res = self.ok(self.tn("git", "remote", "ls", "--json", cwd=r))
        self.assertEqual(res.json, [
            {"name": "gitlab", "url": "git@gitlab.example.com:acme/shop-web.git",
             "forge": "work", "path": "acme/shop-web",
             "web": "https://gitlab.example.com/acme/shop-web"},
            {"name": "other", "url": "https://code.example.org/x/y.git", "forge": None,
             "path": None, "web": None}])
        text = self.ok(self.tn("git", "remote", "ls", cwd=r))
        self.assertTrue(text.stdout.startswith("NAME"))

    def test_empty(self):
        r = self.ok(self.tn("git", "remote", "ls", cwd=self.repo()))
        self.assertEqual(r.stdout, "")
        self.assertIn("No remotes", r.stderr)


class Open(GitCase):
    def setUp(self):
        super().setUp()
        self.r = self.repo("shop-web")

    def add(self, name, url):
        self.git(self.r, "remote", "add", name, url)

    def test_pages_per_forge_kind(self):
        self.add("gitlab", "git@gitlab.example.com:acme/shop-web.git")
        self.add("github", "https://github.com/alex/shop-web.git")
        self.add("bb", "ssh://git@bitbucket.org/alex/acme-shop-web.git")
        cases = [
            ("gitlab", "repo", "https://gitlab.example.com/acme/shop-web"),
            ("gitlab", "pr", "https://gitlab.example.com/acme/shop-web/-/merge_requests"),
            ("gitlab", "ci", "https://gitlab.example.com/acme/shop-web/-/pipelines"),
            ("github", "pr", "https://github.com/alex/shop-web/pulls"),
            ("github", "ci", "https://github.com/alex/shop-web/actions"),
            ("github", "issues", "https://github.com/alex/shop-web/issues"),
            ("bb", "pr", "https://bitbucket.org/alex/acme-shop-web/pull-requests"),
            ("bb", "ci", "https://bitbucket.org/alex/acme-shop-web/pipelines"),
        ]
        for remote, page, url in cases:
            r = self.ok(self.tn("git", "open", page, "--remote", remote, "--print", cwd=self.r))
            self.assertEqual(r.stdout.strip(), url)

    def test_default_remote_origin_then_first(self):
        self.add("zeta", "git@gitlab.example.com:a/zeta.git")
        self.add("origin", "https://github.com/alex/x.git")
        r = self.ok(self.tn("git", "open", "--json", cwd=self.r))
        self.assertEqual(r.json, {"url": "https://github.com/alex/x", "remote": "origin",
                                  "forge": "gh"})
        self.git(self.r, "remote", "remove", "origin")
        r = self.ok(self.tn("git", "open", "--json", cwd=self.r))
        self.assertEqual(r.json["remote"], "zeta")

    def test_opens_the_browser(self):
        self.add("origin", "https://github.com/alex/x.git")
        with mock.patch.object(gitplugin, "_browse", return_value=True) as browse:
            r = self.ok(self.tn("git", "open", "pr", cwd=self.r))
        browse.assert_called_once_with("https://github.com/alex/x/pulls")
        self.assertEqual(r.stdout.strip(), "https://github.com/alex/x/pulls")

    def test_over_ssh_only_prints(self):
        self.add("origin", "https://github.com/alex/x.git")
        with mock.patch.object(gitplugin, "_browse") as browse:
            r = self.ok(self.tn("git", "open", cwd=self.r, env={"SSH_CONNECTION": "1 2 3 4"}))
            self.ok(self.tn("git", "open", "--dry-run", cwd=self.r))
        browse.assert_not_called()
        self.assertEqual(r.stdout.strip(), "https://github.com/alex/x")

    def test_unknown_host(self):
        self.add("origin", "https://code.example.org/x/y.git")
        r = self.tn("git", "open", "--json", cwd=self.r)
        self.assertExit(r, 1)
        self.assertEqual(r.error["message"], "no forge in config for host code.example.org")

    def test_no_remotes_and_bad_page(self):
        self.assertExit(self.tn("git", "open", "--print", cwd=self.r), 1)
        self.assertExit(self.tn("git", "open", "wiki", cwd=self.r), 2)
