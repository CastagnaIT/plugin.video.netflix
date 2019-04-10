# Contributing to plugin.video.netflix

Please take a moment to review this document in order to make the contribution
process easy and effective for everyone involved.

Following these guidelines helps to communicate that you respect the time of
the developers managing and developing this open source project. In return,
they should reciprocate that respect in addressing your issue, assessing
changes, and helping you finalize your pull requests.

As for everything else in the project, the contributions are governed by our
[Code of Conduct](Code_of_Conduct.md).

## Using the issue tracker

First things first: **Do NOT report security vulnerabilities in public issues!**
Please disclose responsibly by letting
[us](mailto:public@asciidisco.com?subject=NetflixPluginSecurity) know upfront.
We will assess the issue as soon as possible on a best-effort basis and will
give you an estimate for when we have a fix and release available for an
eventual public disclosure.

The issue tracker is the preferred channel for [bug reports](#bugs),
[features requests](#features) and [submitting pull
requests](#pull-requests), but please respect the following restrictions:

* Please **do not** use the issue tracker for personal support requests.

* Please **do not** derail or troll issues. Keep the discussion on topic and
  respect the opinions of others.

## Bug reports

A bug is a _demonstrable problem_ that is caused by the code in the repository.
Good bug reports are extremely helpful - thank you!

Guidelines for bug reports:

* **Use the GitHub issue search** &mdash; check if the issue has already been reported.
* **Check if the issue has been fixed** &mdash; try to reproduce it using `master`.
* **Isolate the problem** &mdash; ideally create a reduced test case.

A good bug report shouldn't leave others needing to chase you up for more
information. Please try to be as detailed as possible in your report. What is
your environment? What steps will reproduce the issue? What OS experiences the
problem? What would you expect to be the outcome? All these details will help
people to fix any potential bugs.

Example:

> Short and descriptive example bug report title
>
> A summary of the issue and the Kodi & the OS/Processor Arch
> environment in which it occurs. If
> suitable, include the steps required to reproduce the bug.
>
> `This is the first step`
> `This is the second step`
> `Further steps, etc.`
>
> `<log>` - a link to the Kodi debug log
>
> Any other information you want to share that is relevant to the issue being
> reported. This might include the lines of code that you have identified as
> causing the bug, and potential solutions (and your opinions on their
> merits).

## Feature requests

Feature requests are welcome. But take a moment to find out whether your idea
fits with the scope and aims of the project. It's up to *you* to make a strong
case to convince the project's developers of the merits of this feature. Please
provide as much detail and context as possible.

## Pull requests

Good pull requests - patches, improvements, new features - are a fantastic
help. They should remain focused in scope and avoid containing unrelated
commits.

**Please ask first** before embarking on any significant pull request (e.g.
implementing features, refactoring code), otherwise you risk spending a lot of
time working on something that the project's developers might not want to merge
into the project.

### For new Contributors

If you never created a pull request before, welcome :tada: :smile:
[Here is a great tutorial](https://egghead.io/series/how-to-contribute-to-an-open-source-project-on-github)
on how to send one :)

* [Fork](http://help.github.com/fork-a-repo/), clone, and configure the remotes:

```bash
# Clone your fork of the repo into the current directory
git clone https://github.com/<your-username>/<repo-name>
# Navigate to the newly cloned directory
cd <repo-name>
# Assign the original repo to a remote called "upstream"
git remote add upstream https://github.com/asciidisco/plugin.video.netflix
```

* If you cloned a while ago, get the latest changes from upstream:

   ```bash
   git checkout master
   git pull upstream master
   ```

* Create a new topic branch (off the main project development branch) to
   contain your feature, change, or fix:

   ```bash
   git checkout -b <topic-branch-name>
   ```

* Make sure to update, or add to the tests when appropriate. Patches and
   features will not be accepted without tests. Run `make test` to check that
   all tests pass after you've made changes.Run `make lint` to ensure
   that your code meets our guildelines (PEP-8)

* If you added or changed a feature, make sure to document it accordingly in
   the `README.md` file.

* Push your topic branch up to your fork:

   ```bash
   git push origin <topic-branch-name>
   ```

* Note: We follow Angular style commit guildelines

  Best to install NodeJS & use commitizen for that, all you need to do is

   ```bash
   npm install
   ```

   initially in the root directiory & then use

   ```bash
   make commit
   ```

   to commit changes.

* [Open a Pull Request](https://help.github.com/articles/using-pull-requests/)
    with a clear title and description.

### Addendum

Optionally, you can help us with these things. But don’t worry if they are too
complicated, we can help you out and teach you as we go :)

* Update your branch to the latest changes in the upstream master branch. You
   can do that locally with

   ```bash
   git pull --rebase upstream master
   ```

   Afterwards force push your changes to your remote feature branch.

* Once a pull request is good to go, you can tidy up your commit messages using
   Git's [interactive rebase](https://help.github.com/articles/interactive-rebase).
   Please follow our commit message conventions shown below, as they are used by
   [semantic-release](https://github.com/semantic-release/semantic-release) to
   automatically determine the new version and release to npm. In a nutshell:

#### Commit Message Conventions

* Commit test files with `test: ...` or `test(scope): ...` prefix
* Commit bug fixes with `fix: ...` or `fix(scope): ...` prefix
* Commit breaking changes by adding `BREAKING CHANGE:` in the commit body
    (not the subject line)
* Commit changes to `package.json`, `.gitignore` and other meta files with
    `chore(filenamewithoutext): ...`
* Commit changes to README files or comments with `docs: ...`
* Cody style changes with `style: standard`

**IMPORTANT**: By submitting a patch, you agree to license your work under the
same license as that used by the project.

## Maintainers

If you have commit access, please follow this process for
merging patches and cutting new releases.

### Reviewing changes

* Check that a change is within the scope and philosophy of the component.
* Check that a change has any necessary tests.
* Check that a change has any necessary documentation.
* If there is anything you don’t like, leave a comment below the respective
   lines and submit a "Request changes" review. Repeat until everything has
   been addressed.
* If you are not sure about something, mention `@asciidisco` or specific
   people for help in a comment.
* If there is only a tiny change left before you can merge it and you think
   it’s best to fix it yourself, you can directly commit to the author’s fork.
   Leave a comment about it so the author and others will know.
* Once everything looks good, add an "Approve" review. Don’t forget to say
   something nice 👏🐶💖✨
* If the commit messages follow [our conventions](@commit-message-conventions)

* If there is a breaking change, make sure that `BREAKING CHANGE:` with
    _exactly_ that spelling (incl. the ":") is in body of the according
    commit message. This is _very important_, better look twice :)
* Make sure there are `fix: ...` or `feat: ...` commits depending on whether
    a bug was fixed or a feature was added. **Gotcha:** look for spaces before
    the prefixes of `fix:` and `feat:`, these get ignored by semantic-release.
* Use the "Rebase and merge" button to merge the pull request.
* Done! You are awesome! Thanks so much for your help 🤗

* If the commit messages _do not_ follow our conventions

* Use the "squash and merge" button to clean up the commits and merge at
    the same time: ✨🎩
* Is there a breaking change? Describe it in the commit body. Start with
    _exactly_ `BREAKING CHANGE:` followed by an empty line. For the commit
    subject:
* Was a new feature added? Use `feat: ...` prefix in the commit subject
* Was a bug fixed? Use `fix: ...` in the commit subject

Sometimes there might be a good reason to merge changes locally. The process
looks like this:

### Reviewing and merging changes locally

```bash
git checkout master # or the main branch configured on github
git pull # get latest changes
git checkout feature-branch # replace name with your branch
git rebase master
git checkout master
git merge feature-branch # replace name with your branch
git push
```

When merging PRs from forked repositories, we recommend you install the
[hub](https://github.com/github/hub) command line tools.

This allows you to do:

```bash
hub checkout link-to-pull-request
```

meaning that you will automatically check out the branch for the pull request,
without needing any other steps like setting git upstreams! :sparkles:
