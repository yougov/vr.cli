"""
Command-line API for Velociraptor. Wraps behavior from v1 API
in routines for performing common operations. Invoke using
the `vr.cli` console entry point or with `python -m vr.cli`.
"""

from __future__ import print_function

import pprint
import argparse
import logging
import warnings

from six.moves import map

import datadiff
import jaraco.logging
from more_itertools.recipes import consume
from jaraco import timing
from jaraco.ui import cmdline, progress
from jaraco.functools import once

from vr.common import models


class FilterExcludeAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        namespace.filter.exclusions.append(values)


class Swarm(cmdline.Command):
    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('filter', type=models.SwarmFilter)
        parser.add_argument('tag')
        parser.add_argument('-x', '--exclude', action=FilterExcludeAction)
        parser.add_argument(
            '--countdown', action="store_true",
            default=False,
            help="Give a 5 second countdown before dispatching swarms.",
        )

    @classmethod
    def run(cls, args):
        swarms = _get_swarms(args)
        matched = list(args.filter.matches(swarms))
        print("Matched", len(matched), "apps")
        pprint.pprint(matched)
        if args.countdown:
            progress.countdown("Reswarming in {} sec")
        changes = dict()
        if args.tag != '-':
            changes['version'] = args.tag
        [swarm.dispatch(**changes) for swarm in matched]


class Build(cmdline.Command):
    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('app')
        parser.add_argument('tag')

    @classmethod
    def run(cls, args):
        warnings.warn("Build command fails for containerized apps; see #189")
        build = models.Build._for_app_and_tag(args.vr, args.app, args.tag)
        build.assemble()


class RebuildAll(cmdline.Command):
    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('filter', type=models.SwarmFilter)
        parser.add_argument('-x', '--exclude', action=FilterExcludeAction)
        parser.add_argument(
            '--countdown', action="store_true",
            default=False,
            help="Give a 5 second countdown before dispatching swarms.",
        )

    @classmethod
    def run(cls, args):
        swarms = _get_swarms(args)
        swarms = list(args.filter.matches(swarms))
        print("Matched", len(swarms), "apps")
        pprint.pprint(swarms)
        if args.countdown:
            progress.countdown("Rebuilding in {} sec")
        builds = [swarm.new_build() for swarm in swarms]
        for build in set(builds):
            build.assemble()
        for swarm in swarms:
            swarm.dispatch()


class FilterParam(object):

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('filter', type=models.SwarmFilter, nargs='?',
            default=models.SwarmFilter())


class Procs(FilterParam, cmdline.Command):

    swarmtmpl = '{swarm.name} [{swarm.version}]'
    proctmpl = '{host:<22}  {port:<5}  {statename:<9}  {description}'

    @classmethod
    def add_arguments(cls, parser):
        method_lookup = lambda val: getattr(cls, '_'+val)
        parser.add_argument('method', type=method_lookup)
        parser.add_argument('--host', type=models.ProcHostFilter,
            default=models.ProcHostFilter(),
            help='Apply actions to this host only')
        super(Procs, cls).add_arguments(parser)

    @classmethod
    def run(cls, args):
        all_swarms = _get_swarms(args)
        swarms = args.filter.matches(all_swarms)
        command = cls(args.host)
        for swarm in swarms:
            args.method(command, swarm)

    @staticmethod
    def _get_proc_from_dict(proc):
        host = models.Host(proc['host'])
        return host.get_proc(proc['group'])

    def __init__(self, proc_filter):
        self.proc_filter = proc_filter

    @classmethod
    def print_swarm(cls, swarm):
        print()
        print(cls.swarmtmpl.format(**vars()))

    def _list(self, swarm):
        print_swarm = once(lambda swarm: self.print_swarm(swarm))
        for proc in self.proc_filter.matches(swarm.procs):
            print_swarm(swarm)
            print('  ' + self.proctmpl.format(**proc))

    def _exec(self, proc_method, swarm):
        print_swarm = once(lambda swarm: self.print_swarm(swarm))
        for proc in self.proc_filter.matches(swarm.procs):
            print_swarm(swarm)
            print(proc_method.upper() + ' ' + self.proctmpl.format(**proc))
            getattr(self._get_proc_from_dict(proc), proc_method)()

    def _start(self, swarm):
        return self._exec('start', swarm)

    def _stop(self, swarm):
        return self._exec('stop', swarm)

    def _restart(self, swarm):
        return self._exec('restart', swarm)


class ListSwarms(FilterParam, cmdline.Command):

    @classmethod
    def run(cls, args):
        with timing.Stopwatch() as watch:
            all_swarms = _get_swarms(args)
        tmpl = "Loaded {n_swarms} swarms in {watch.elapsed}"
        msg = tmpl.format(n_swarms=len(all_swarms), watch=watch)
        print(msg)
        filtered_swarms = args.filter.matches(all_swarms)
        consume(map(print, sorted(filtered_swarms)))


class Uptests(cmdline.Command):

    @classmethod
    def run(cls, args):
        resp = args.vr.load('/api/v1/testruns/latest/')
        results = resp['testresults']
        for result in results:
            if not result['passed']:
                print("{procname} failed:".format(**result))
                print(result['results'])


class Deploy(cmdline.Command):

    @staticmethod
    def find_release(spec):
        if not spec.isdigit():
            raise NotImplementedError("Release spec must be a release ID")
        return int(spec)

    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('release', type=cls.find_release)
        parser.add_argument('host')
        parser.add_argument('port', type=int)
        parser.add_argument('proc')
        parser.add_argument('-c', '--config-name', default='prod')

    @classmethod
    def run(cls, args):
        release = models.Release(args.vr)
        release.load(models.Release.base + str(args.release) + '/')
        release.deploy(args.host, args.port, args.proc, args.config_name)


class CompareReleases(cmdline.Command):
    @classmethod
    def add_arguments(cls, parser):
        parser.add_argument('orig', type=Deploy.find_release)
        parser.add_argument('changed', type=Deploy.find_release)

    @classmethod
    def load_config(cls, args, release_id):
        release = models.Release(args.vr)
        template = models.Release.base + '{release_id}/'
        release.load(template.format(**locals()))
        return release.parsed_config()

    @classmethod
    def run(cls, args):
        orig = cls.load_config(args, args.orig)
        changed = cls.load_config(args, args.changed)
        print(datadiff.diff(orig, changed))


def _get_swarms(args):
    query_tokens = args.filter.split('-')
    keys = ['app__name', 'config_name', 'proc_name']
    params = {}
    for key, val in zip(keys, query_tokens):
        if val != '.*':
            params[key] = val

    logging.info('Searching for swarms: %s', params)
    all_swarms = models.Swarm.load_all(args.vr, params)

    return all_swarms


def handle_command_line():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--url',
        help="Velociraptor URL (defaults to https://deploy, resolved; "
        "override with VELOCIRAPTOR_URL)")
    parser.add_argument(
        '--username',
        help="Override the username used for authentication")
    jaraco.logging.add_arguments(parser)
    cmdline.Command.add_subparsers(parser)
    args = parser.parse_args()
    jaraco.logging.setup(args)
    args.vr = models.Velociraptor(args.url, args.username)
    args.action.run(args)
