Title: Welcome to Click — Click Documentation (8.3.x)

URL Source: https://click.palletsprojects.com/

Markdown Content:
[![Image 1: _images/click-name.svg](https://click.palletsprojects.com/en/stable/_images/click-name.svg)](https://click.palletsprojects.com/en/stable/_images/click-name.svg)
Click is a Python package for creating beautiful command line interfaces in a composable way with as little code as necessary. It’s the “Command Line Interface Creation Kit”. It’s highly configurable but comes with sensible defaults out of the box.

It aims to make the process of writing command line tools quick and fun while also preventing any frustration caused by the inability to implement an intended CLI API.

Click in three points:

*   arbitrary nesting of commands

*   automatic help page generation

*   supports lazy loading of subcommands at runtime

What does it look like? Here is an example of a simple Click program:

import click

@click.command()
@click.option('--count', default=1, help='Number of greetings.')
@click.option('--name', prompt='Your name',
              help='The person to greet.')
def hello(count, name):
 """Simple program that greets NAME for a total of COUNT times."""
    for x in range(count):
        click.echo(f"Hello {name}!")

if  __name__  == '__main__':
    hello()

And what it looks like when run:

$ python hello.py --count=3
Your name: John
Hello John!
Hello John!
Hello John!

It automatically generates nicely formatted help pages:

$ python hello.py --help
Usage: hello.py [OPTIONS]

 Simple program that greets NAME for a total of COUNT times.

Options:
 --count INTEGER Number of greetings.
 --name TEXT The person to greet.
 --help Show this message and exit.

You can get the library directly from PyPI:

pip install click

Documentation[¶](https://click.palletsprojects.com/#documentation "Link to this heading")
-----------------------------------------------------------------------------------------

*   [Frequently Asked Questions](https://click.palletsprojects.com/en/stable/faqs/)
    *   [General](https://click.palletsprojects.com/en/stable/faqs/#general)

Tutorials[¶](https://click.palletsprojects.com/#tutorials "Link to this heading")
---------------------------------------------------------------------------------

*   [Quickstart](https://click.palletsprojects.com/en/stable/quickstart/)
*   [Virtualenv](https://click.palletsprojects.com/en/stable/virtualenv/)

How to Guides[¶](https://click.palletsprojects.com/#how-to-guides "Link to this heading")
-----------------------------------------------------------------------------------------

*   [Packaging Entry Points](https://click.palletsprojects.com/en/stable/entry-points/)
*   [Setuptools Integration](https://click.palletsprojects.com/en/stable/setuptools/)
*   [Upgrade Guides](https://click.palletsprojects.com/en/stable/upgrade-guides/)
*   [Supporting Multiple Versions](https://click.palletsprojects.com/en/stable/support-multiple-versions/)

Conceptual Guides[¶](https://click.palletsprojects.com/#conceptual-guides "Link to this heading")
-------------------------------------------------------------------------------------------------

*   [CLI Design Opinions](https://click.palletsprojects.com/en/stable/design-opinions/)
*   [Why Click?](https://click.palletsprojects.com/en/stable/why/)
*   [Click Concepts](https://click.palletsprojects.com/en/stable/click-concepts/)

General Reference[¶](https://click.palletsprojects.com/#general-reference "Link to this heading")
-------------------------------------------------------------------------------------------------

*   [Parameters](https://click.palletsprojects.com/en/stable/parameters/)
*   [Parameter Types](https://click.palletsprojects.com/en/stable/parameter-types/)
*   [Options](https://click.palletsprojects.com/en/stable/options/)
*   [Options Shortcut Decorators](https://click.palletsprojects.com/en/stable/option-decorators/)
*   [Arguments](https://click.palletsprojects.com/en/stable/arguments/)
*   [Basic Commands, Groups, Context](https://click.palletsprojects.com/en/stable/commands-and-groups/)
*   [Advanced Groups and Context](https://click.palletsprojects.com/en/stable/commands/)
*   [Help Pages](https://click.palletsprojects.com/en/stable/documentation/)
*   [User Input Prompts](https://click.palletsprojects.com/en/stable/prompts/)
*   [Handling Files](https://click.palletsprojects.com/en/stable/handling-files/)
*   [Advanced Patterns](https://click.palletsprojects.com/en/stable/advanced/)
*   [Complex Applications](https://click.palletsprojects.com/en/stable/complex/)
*   [Extending Click](https://click.palletsprojects.com/en/stable/extending-click/)
*   [Testing Click Applications](https://click.palletsprojects.com/en/stable/testing/)
*   [Utilities](https://click.palletsprojects.com/en/stable/utils/)
*   [Shell Completion](https://click.palletsprojects.com/en/stable/shell-completion/)
*   [Exception Handling and Exit Codes](https://click.palletsprojects.com/en/stable/exceptions/)
*   [General Command Line Topics](https://click.palletsprojects.com/en/stable/command-line-reference/)
*   [Unicode Support](https://click.palletsprojects.com/en/stable/unicode-support/)
*   [Windows Console Notes](https://click.palletsprojects.com/en/stable/wincmd/)

API Reference[¶](https://click.palletsprojects.com/#api-reference "Link to this heading")
-----------------------------------------------------------------------------------------

*   [API](https://click.palletsprojects.com/en/stable/api/)
    *   [Decorators](https://click.palletsprojects.com/en/stable/api/#decorators)
    *   [Utilities](https://click.palletsprojects.com/en/stable/api/#utilities)
    *   [Commands](https://click.palletsprojects.com/en/stable/api/#commands)
    *   [Parameters](https://click.palletsprojects.com/en/stable/api/#parameters)
    *   [Context](https://click.palletsprojects.com/en/stable/api/#context)
    *   [Types](https://click.palletsprojects.com/en/stable/api/#types)
    *   [Exceptions](https://click.palletsprojects.com/en/stable/api/#exceptions)
    *   [Formatting](https://click.palletsprojects.com/en/stable/api/#formatting)
    *   [Parsing](https://click.palletsprojects.com/en/stable/api/#parsing)
    *   [Shell Completion](https://click.palletsprojects.com/en/stable/api/#shell-completion)
    *   [Testing](https://click.palletsprojects.com/en/stable/api/#testing)

About Project[¶](https://click.palletsprojects.com/#about-project "Link to this heading")
-----------------------------------------------------------------------------------------

*   This documentation is structured according to [Diataxis](https://diataxis.fr/) and written with [MyST](https://myst-parser.readthedocs.io/en/latest/)

*   [Version Policy](https://palletsprojects.com/versions)

*   [Contributing](https://palletsprojects.com/contributing/)

*   [Donate](https://palletsprojects.com/donate)

*   [click-contrib](https://click.palletsprojects.com/en/stable/contrib/)
*   [BSD-3-Clause License](https://click.palletsprojects.com/en/stable/license/)
*   [Changes](https://click.palletsprojects.com/en/stable/changes/)
