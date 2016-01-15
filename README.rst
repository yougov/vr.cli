vr.cli
======

A command-line interface for wrangling Velociraptor swarms and automating
some common operations.

Implementation
==============

The cli provides a command-line interface around the vr.common.models.

Features
========

``vr.cli`` supports several sub-commands, including:

 - build
 - swarm
 - uptests

For a complete list of commands, invoke vr.cli with --help.

Build
-----

Simply assemble a build of an app at a given tag. This routine is useful to
prime an build before doing other swarm operations.

Swarm
-----

This routine dispatch a swarm at a given tag::

    vr.cli swarm MyApp-Recipe_.* 3.0 -x Recipe_Skipped

It takes as its parameters a filter of swarm name, a version number, and
optionally some excludes.

The name filter is case sensitive, but the excludes are case insensitive.

Uptests
-------

This routine will provide a quick printout of all failing uptests.

Procs
-----

List, start, or stop procs.

Compare Releases
----------------

Compare the configuration of any two releases (indicated by release ID).


Configuration
=============

The ``vr.cli`` command requires a URL to communicate with the
Velociraptor instance via its REST api. By default, the URL is inferred from
the name ``deploy`` as resolved by DNS. If ``deploy`` resolves as
``deploy.example.com``, ``vr.cli`` will use https://deploy.example.com as
the URL. The value can be overridden by passing ``--url`` to the command or by
setting the ``VELOCIRAPTOR_URL`` environment variable.

Authentication
--------------

The Velociraptor client models (found in vr.common.models) will default to
using the current username (getpass.getuser). If your username on your local
host doesn't match your username in Velociraptor, you can override the
username by passing ``--username`` to the command or by setting any of the
`environment variables searched by getuser
<https://docs.python.org/2/library/getpass.html#getpass.getuser>`_.

``vr.cli`` also leverages keyring to avoid entering passwords each time.
To do this, it needs a system name and username. For the username, it uses
the username resolved above. For the system name, it defaults to the domain
name of the Velociraptor URL (as resolved above). The domain can be overridden
by setting the ``VELOCIRAPTOR_AUTH_DOMAIN`` environment variable.
