from __future__ import print_function

from functools import partial
import pprint
import argparse

from six.moves import map

import datadiff
from jaraco.util import cmdline
from jaraco.util import ui
from jaraco.util import timing
from more_itertools.recipes import consume

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
        swarms = models.Swarm.load_all(args.vr)
        matched = list(args.filter.matches(swarms))
        print("Matched", len(matched), "apps")
        pprint.pprint(matched)
        if args.countdown:
            ui.countdown("Reswarming in {} sec")
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
        swarms = models.Swarm.load_all(args.vr)
        swarms = list(args.filter.matches(swarms))
        print("Matched", len(swarms), "apps")
        pprint.pprint(swarms)
        if args.countdown:
            models.countdown("Rebuilding in {} sec")
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

    proctmpl = (
        '{app_name}-{config_name}-{proc_name} [{version}]    '
        '{host:<22}  {port:<5}  {statename:<9}  {description}')

    @classmethod
    def add_arguments(cls, parser):
        action_lookup = dict(
            list=cls._list,
            stop=partial(cls._exec, 'stop'),
            start=partial(cls._exec, 'start'),
            restart=partial(cls._exec, 'restart'),
        )
        parser.add_argument('subcmd', type=lambda val: action_lookup[val])
        parser.add_argument('--host', default=None,
                            help='Apply actions to this host only')
        super(Procs, cls).add_arguments(parser)

    @classmethod
    def run(cls, args):
        all_swarms = models.Swarm.load_all(args.vr)
        swarms = args.filter.matches(all_swarms)
        procs = []
        for swarm in swarms:
            for proc in swarm.procs:
                if args.host is None or args.host == proc['host']:
                    procs.append(proc)
        consume(map(args.subcmd, procs))

    @staticmethod
    def _get_proc_from_dict(proc):
        host = models.Host(proc['host'])
        return host.get_proc(proc['group'])

    @classmethod
    def _list(cls, proc):
        print(cls.proctmpl.format(**proc))

    @classmethod
    def _exec(cls, proc_method, proc):
        print(proc_method.upper() + ' ' + cls.proctmpl.format(**proc))
        getattr(cls._get_proc_from_dict(proc), proc_method)()


class ListSwarms(FilterParam, cmdline.Command):

    @classmethod
    def run(cls, args):
        with timing.Stopwatch() as watch:
            all_swarms = models.Swarm.load_all(args.vr)
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


def handle_command_line():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url',
        help="Velociraptor URL (defaults to https://deploy, resolved; "
            "override with VELOCIRAPTOR_URL)")
    parser.add_argument('--username',
        help="Override the username used for authentication")
    cmdline.Command.add_subparsers(parser)
    args = parser.parse_args()
    args.vr = models.Velociraptor(args.url, args.username)
    args.action.run(args)
