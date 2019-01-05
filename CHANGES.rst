3.4
---

Pin against vr.common 6 for namespace compatibility.

3.3
---

Removed deprecated dependencies and refreshed package metadata.

3.2
---

Add support for selecting swarms by ingredients they use.

3.1
---

#2: Add support for adding and removing ingredients when
dispatching a swarm.

3.0
---

Drop support for Python 3.4 and earlier (including Python 2).

2.11
----

Allow username to be supplied by environment variable also.

2.10
----

Bump to vr.common 5.1 to allow credentials to be supplied by
environment variables.

2.9
---

First release following move to Github. Incorporated `project
skeleton from jaraco <https://github.com/jaraco/skeleton>`_.
Enabled automatic releases of tagged commits.

2.8
---

Remove warning in build about containerized apps now that the
issue is fixed

2.7.2
-----

Fixed issue where regular expressions were being passed in the
search parameters, preventing matches. Now any fields that
appear to have regular expressions are excluded.

2.7.1
-----

Fixed issue where lack of ``-v`` would result in a TypeError on
Python 3. Instead, use ``--log-level`` (or simply ``-l``) to
set the log level with something like "INFO" or "debug".

Bump dependency on vr.common fixing another issue on Python 3.

2.7
---

Filter on specific query parameters when loading swarms. Improves
speed of queries involving swarms.

2.6
---

Meta updates to packaging and testing.

2.5
---

Removed dependency on jaraco.util (using smaller packages instead).

2.4
---

Added ``--host`` parameter to ``procs list`` command.

2.3
---

Eliminate dependency on pyyaml.

2.2
---

Use datadiff 1.1.6.

2.1
---

Added ``compare-releases`` command.

2.0
---

Added procs command for listing and controlling procs.

``list-procs`` command replaced by ``procs list`` command.

1.0
---

Initial release ported from cagey 3.1.
