Title: HTTPX

URL Source: https://www.python-httpx.org/

Markdown Content:
![Image 1: HTTPX](https://raw.githubusercontent.com/encode/httpx/master/docs/img/butterfly.png)

* * *

[![Image 2: Test Suite](https://github.com/encode/httpx/workflows/Test%20Suite/badge.svg)](https://github.com/encode/httpx/actions)[![Image 3: Package version](https://badge.fury.io/py/httpx.svg)](https://pypi.org/project/httpx/)

_A next-generation HTTP client for Python._

HTTPX is a fully featured HTTP client for Python 3, which provides sync and async APIs, and support for both HTTP/1.1 and HTTP/2.

* * *

Install HTTPX using pip:

```
$ pip install httpx
```

Now, let's get started:

```
>>> import httpx
>>> r = httpx.get('https://www.example.org/')
>>> r
<Response [200 OK]>
>>> r.status_code
200
>>> r.headers['content-type']
'text/html; charset=UTF-8'
>>> r.text
'<!doctype html>\n<html>\n<head>\n<title>Example Domain</title>...'
```

Or, using the command-line client.

```
# The command line client is an optional dependency.
$ pip install 'httpx[cli]'
```

Which now allows us to use HTTPX directly from the command-line...

![Image 4: httpx --help](https://www.python-httpx.org/img/httpx-help.png)

Sending a request...

![Image 5: httpx http://httpbin.org/json](https://www.python-httpx.org/img/httpx-request.png)

Features
--------

HTTPX builds on the well-established usability of `requests`, and gives you:

*   A broadly [requests-compatible API](https://www.python-httpx.org/compatibility/).
*   Standard synchronous interface, but with [async support if you need it](https://www.python-httpx.org/async/).
*   HTTP/1.1 [and HTTP/2 support](https://www.python-httpx.org/http2/).
*   Ability to make requests directly to [WSGI applications](https://www.python-httpx.org/advanced/transports/#wsgi-transport) or [ASGI applications](https://www.python-httpx.org/advanced/transports/#asgi-transport).
*   Strict timeouts everywhere.
*   Fully type annotated.
*   100% test coverage.

Plus all the standard features of `requests`...

*   International Domains and URLs
*   Keep-Alive & Connection Pooling
*   Sessions with Cookie Persistence
*   Browser-style SSL Verification
*   Basic/Digest Authentication
*   Elegant Key/Value Cookies
*   Automatic Decompression
*   Automatic Content Decoding
*   Unicode Response Bodies
*   Multipart File Uploads
*   HTTP(S) Proxy Support
*   Connection Timeouts
*   Streaming Downloads
*   .netrc Support
*   Chunked Requests

Documentation
-------------

For a run-through of all the basics, head over to the [QuickStart](https://www.python-httpx.org/quickstart/).

For more advanced topics, see the **Advanced** section, the [async support](https://www.python-httpx.org/async/) section, or the [HTTP/2](https://www.python-httpx.org/http2/) section.

The [Developer Interface](https://www.python-httpx.org/api/) provides a comprehensive API reference.

To find out about tools that integrate with HTTPX, see [Third Party Packages](https://www.python-httpx.org/third_party_packages/).

Dependencies
------------

The HTTPX project relies on these excellent libraries:

*   `httpcore` - The underlying transport implementation for `httpx`.
*   `h11` - HTTP/1.1 support.
*   `certifi` - SSL certificates.
*   `idna` - Internationalized domain name support.
*   `sniffio` - Async library autodetection.

As well as these optional installs:

*   `h2` - HTTP/2 support. _(Optional, with `httpx[http2]`)_
*   `socksio` - SOCKS proxy support. _(Optional, with `httpx[socks]`)_
*   `rich` - Rich terminal support. _(Optional, with `httpx[cli]`)_
*   `click` - Command line client support. _(Optional, with `httpx[cli]`)_
*   `brotli` or `brotlicffi` - Decoding for "brotli" compressed responses. _(Optional, with `httpx[brotli]`)_
*   `zstandard` - Decoding for "zstd" compressed responses. _(Optional, with `httpx[zstd]`)_

A huge amount of credit is due to `requests` for the API layout that much of this work follows, as well as to `urllib3` for plenty of design inspiration around the lower-level networking details.

Installation
------------

Install with pip:

```
$ pip install httpx
```

Or, to include the optional HTTP/2 support, use:

```
$ pip install httpx[http2]
```

To include the optional brotli and zstandard decoders support, use:

```
$ pip install httpx[brotli,zstd]
```

HTTPX requires Python 3.9+
