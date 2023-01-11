# Upload Charm Documentation

*This action is still in alpha, breaking changes could occur.*

This action automates uploading documentation from the `docs` folder in a
repository to discourse which is how the charm documentation is published to
charmhub.

## Getting Started

### Sync docs

1. Create the `docs` folder in the repository.
2. Optionally, create a file `docs/index.md` for any content you would like to
    display above the navigation table on discourse. This content does not get
    published to charmhub and is only visible on discourse.
3. Within the `docs` folder, create directories for page groups (e.g., for all
    tutorials) and markdown files (`*.md`) for individual pages. On charmhub,
    the groupings on the navigation panel will be named based on the name of
    the directory after replacing `_` and `-` with spaces and appliying the
    [`str.title`](https://docs.python.org/3/library/stdtypes.html#str.title)
    function to it. The name of pages is based on whatever of the following is
    available, in order: (1) the first level 1 heading (e.g., `# <heading>`) in
    the file, the first line in the file or the name of the file treated in the
    same way as the name of groupings.

    If you have existing documentation on discourse, you can retrieve the
    markdown version by changing the link to the topic in your browser from
    `https://discourse.charmhub.io/t/<slug>/<topic id>` to
    `https://discourse.charmhub.io/raw/<topic id>`. *Future plans for this
    action include automating this migration by pulling the content down and
    creating a PR for you to review in the repository.*

    Note that the action may change the order of how groups and pages are
    displayed in the navigation pane. The action will sort them alphabetically.
4. Optionally, remove the current `docs` key from `metadata.yaml` if you would
    like the action to create its own topics on discourse rather than re-use
    any existing topics. This means that if, for some reason, you don't like
    what the action does, you can easily revert back to the previous
    documentation. Be sure to file an issue with the reason if the action does
    something unexpected or you would prefer it to do something different.
5. Add this action to your desired workflow. For example:

    ```yaml
    jobs:
      publish-docs:
        name: Publish docs
        runs-on: ubuntu-22.04
        steps:
          - uses: actions/checkout@v3
          - name: Publish documentation
            uses: canonical/upload-charm-docs@main
            id: publishDocumentation
            with:
              discourse_host: discourse.charmhub.io
              discourse_api_username: ${{ secrets.DISCOURSE_API_USERNAME }}
              discourse_api_key: ${{ secrets.DISCOURSE_API_KEY }}
          - name: Show index page
            run: echo '${{ steps.publishDocumentation.outputs.index_url }}'
    ```

    This action requires an API username and key to discourse. For Canonical
    staff, please file a ticket with IS to request one. Note that there is a
    rate limit on the number of topics that can be created by a user per day on
    discourse. If you encounter this issue, the action will fail and report
    that as the reason. It may help to space out adopting this action if you
    are planning to use it for multiple charms or to use different users for
    each charm. Note that other rate limits also apply which is why execution
    might look like it is stalled for a short period and then resume. The
    action will gracefully wait in case of throttling up to a maximum of 10
    minutes.

    There is a nice parameter, `dry_run`, which will do everything except
    make changes on discourse and log what would have happened. This will help
    you see what the action would have done.
6. Check the logs for the URL to the index topic that the action created. This
    is also available under the `index_url` output of the action. This needs to
    be added to the `metadata.yaml` under the `docs` key.

### Migrate docs

1. Create a `docs` key in `metadata.yaml` with the link to the documentation on
    charmhub.
2. Add the action to your desired workflow as mentioned in step 5 of
    [Sync docs section](#sync-docs) with github_token. For example:

    ```yaml
    jobs:
      publish-docs:
        name: Publish docs
        runs-on: ubuntu-22.04
        steps:
          - uses: actions/checkout@v3
          - name: Publish documentation
            uses: canonical/upload-charm-docs@main
            id: publishDocumentation
            with:
              discourse_host: discourse.charmhub.io
              discourse_api_username: ${{ secrets.DISCOURSE_API_USERNAME }}
              discourse_api_key: ${{ secrets.DISCOURSE_API_KEY }}
              github_token: ${{ secrets.GITHUB_TOKEN }}
    ```

    a branch name with `upload-charm-docs/migrate` will be created and a pull 
    request named `[upload-charm-docs] Migrate charm docs` will be created 
    towards the working branch the workflow was triggered with. 
    In order to ensure that the branches can be created successfully, please 
    make sure that there are no existing branches clashing with the name above.
    Please note that `dry_run` parameter has no effect on migrate mode.

The action will now compare the discourse topics with the files and directories
under the `docs` directory and make any changes based on differences.
Additional recommended steps:

* Add the action in dry run mode to run on every PR. This will mean that you
  will see all the changes that would be made by the PR once you are ready to
  publish a new version of the charm and documentation.
* Add the action in dry run mode on publishes to `edge` to see what changes to
  the documentation will be made once you publish to `stable`.
