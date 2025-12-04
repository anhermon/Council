Title: pytest documentation

URL Source: https://docs.pytest.org/

Markdown Content:
pytest: helps you write better programs[¶](https://docs.pytest.org/#pytest-helps-you-write-better-programs "Link to this heading")
----------------------------------------------------------------------------------------------------------------------------------

The `pytest` framework makes it easy to write small, readable tests, and can scale to support complex functional testing for applications and libraries.

**PyPI package name**: [pytest](https://pypi.org/project/pytest)

A quick example[¶](https://docs.pytest.org/#a-quick-example "Link to this heading")
-----------------------------------------------------------------------------------

# content of test_sample.py
def inc(x):
    return x + 1

def test_answer():
    assert inc(3) == 5

To execute it:

$ pytest
=========================== test session starts ============================
platform linux -- Python 3.x.y, pytest-9.x.y, pluggy-1.x.y
rootdir: /home/sweet/project
collected 1 item

test_sample.py F                                                     [100%]

================================= FAILURES =================================
 _______________________________ test_answer ________________________________

    def test_answer():
>       assert inc(3) == 5
E assert 4 == 5
E + where 4 = inc(3)

test_sample.py:6: AssertionError
========================= short test summary info ==========================
FAILED test_sample.py::test_answer - assert 4 == 5
============================ 1 failed in 0.12s =============================

Due to `pytest`’s detailed assertion introspection, only plain `assert` statements are used. See [Get started](https://docs.pytest.org/en/stable/getting-started.html#getstarted) for a basic introduction to using pytest.

Features[¶](https://docs.pytest.org/#id1 "Link to this heading")
----------------------------------------------------------------

*   Detailed info on failing [assert statements](https://docs.pytest.org/en/stable/how-to/assert.html#assert) (no need to remember `self.assert*` names)

*   [Auto-discovery](https://docs.pytest.org/en/stable/explanation/goodpractices.html#test-discovery) of test modules and functions

*   [Modular fixtures](https://docs.pytest.org/en/stable/reference/fixtures.html#fixture) for managing small or parametrized long-lived test resources

*   Can run [unittest](https://docs.pytest.org/en/stable/how-to/unittest.html#unittest) (including trial) test suites out of the box

*   Python 3.10+ or PyPy 3

*   Rich plugin architecture, with over 1300+ [external plugins](https://docs.pytest.org/en/stable/reference/plugin_list.html#plugin-list) and thriving community

*   [Get started](https://docs.pytest.org/en/stable/getting-started.html#get-started) - install pytest and grasp its basics in just twenty minutes

*   [How-to guides](https://docs.pytest.org/en/stable/how-to/index.html#how-to) - step-by-step guides, covering a vast range of use-cases and needs

*   [Reference guides](https://docs.pytest.org/en/stable/reference/index.html#reference) - includes the complete pytest API reference, lists of plugins and more

*   [Explanation](https://docs.pytest.org/en/stable/explanation/index.html#explanation) - background, discussion of key topics, answers to higher-level questions

Bugs/Requests[¶](https://docs.pytest.org/#bugs-requests "Link to this heading")
-------------------------------------------------------------------------------

Please use the [GitHub issue tracker](https://github.com/pytest-dev/pytest/issues) to submit bugs or request features.

Support pytest[¶](https://docs.pytest.org/#support-pytest "Link to this heading")
---------------------------------------------------------------------------------

[Open Collective](https://opencollective.com/) is an online funding platform for open and transparent communities. It provides tools to raise money and share your finances in full transparency.

It is the platform of choice for individuals and companies that want to make one-time or monthly donations directly to the project.

See more details in the [pytest collective](https://opencollective.com/pytest).

pytest for enterprise[¶](https://docs.pytest.org/#pytest-for-enterprise "Link to this heading")
-----------------------------------------------------------------------------------------------

Available as part of the Tidelift Subscription.

The maintainers of pytest and thousands of other packages are working with Tidelift to deliver commercial support and maintenance for the open source dependencies you use to build your applications. Save time, reduce risk, and improve code health, while paying the maintainers of the exact dependencies you use.

[Learn more.](https://tidelift.com/subscription/pkg/pypi-pytest?utm_source=pypi-pytest&utm_medium=referral&utm_campaign=enterprise&utm_term=repo)

### Security[¶](https://docs.pytest.org/#security "Link to this heading")

pytest has never been associated with a security vulnerability, but in any case, to report a security vulnerability please use the [Tidelift security contact](https://tidelift.com/security). Tidelift will coordinate the fix and disclosure.
