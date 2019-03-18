"""
Command-line API for Velociraptor. Wraps behavior from v1 API
in routines for performing common operations. Invoke using
the `vr.cli` console entry point or with `python -m vr.cli`.
"""

from __future__ import print_function

import pprint
import argparse
import logging
import os
from os.path import normpath, basename

from six.moves import map

import datadiff
import jaraco.logging
from more_itertools.recipes import consume
from itertools import chain
from tempora import timing
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
        parser.add_argument('--add-ingredients',
                            default=[],
                            help="List of ingredients to be appended to the "
                                 "end of ingredient list of each swarm.",
                            nargs='+')

        parser.add_argument('--remove-ingredients',
                            default=[],
                            help="List of ingredients to be removed from each "
                                 "swarm.",
                            nargs='+')

        parser.add_argument('--replace-ingredients',
                            default=[],
                            help="List of ingredients to completely replace "
                                 "existing ingredient list for each swarm.",
                            nargs='+')

        parser.add_argument('--by-ingredients',
                            default=[],
                            help="Matches all swarms that include at least "
                                 "one of the ingredients from the list.",
                            nargs='+')
        parser.add_argument(
            '--squad',
            help="Set the squad (API path) when swarming",
        )

    @classmethod
    def run(cls, args):
        swarms = _get_swarms(args)
        assert not (args.replace_ingredients and
                    (args.add_ingredients or args.remove_ingredients)), \
            "Replacing ingredients is mutually exclusive with adding or " \
            "removing them."

        add_ingredients = _resolve_ingredients(args.vr, args.add_ingredients)
        remove_ingredients = _resolve_ingredients(args.vr,
                                                  args.remove_ingredients)
        replace_ingredients = _resolve_ingredients(args.vr,
                                                   args.replace_ingredients)
        by_ingredients = _resolve_ingredients(args.vr,
                                              args.by_ingredients)

        matched = list(args.filter.matches(swarms))
        more_swarms = chain(*[ing.swarms for ing in by_ingredients])
        more_swarms = [models.Swarm.by_id(
            args.vr, basename(normpath(base_url))) for base_url in more_swarms]
        matched = list(set(matched) | set(more_swarms))

        print("Matched", len(matched), "apps")
        pprint.pprint(matched)
        if args.countdown:
            progress.countdown("Reswarming in {} sec")
        changes = dict()
        if args.tag != '-':
            changes['version'] = args.tag
        if args.squad:
            changes['squad'] = args.squad
        if add_ingredients or remove_ingredients:
            add_ingredients = [add.resource_uri for add in add_ingredients]
            remove_ingredients = [add.resource_uri for add in
                                  remove_ingredients]
            assert not (set(add_ingredients) & set(remove_ingredients)), \
                "Can't add and remove same ingredients during a single run"

            for swarm in matched:
                new_ingredients = _assemble_ingredients(
                    swarm.config_ingredients,
                    add_ingredients,
                    remove_ingredients)
                swarm_changes = merge_dicts(changes,
                                            {'config_ingredients':
                                             new_ingredients})
                swarm.dispatch(**swarm_changes)

        else:
            if replace_ingredients:
                changes['config_ingredients'] = [ing.resource_uri for ing
                                                 in replace_ingredients]
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
        parser.add_argument(
            'filter', type=models.SwarmFilter, nargs='?',
            default=models.SwarmFilter())


class Procs(FilterParam, cmdline.Command):

    swarmtmpl = '{swarm.name} [{swarm.version}]'
    proctmpl = '{host:<22}  {port:<5}  {statename:<9}  {description}'

    @classmethod
    def add_arguments(cls, parser):
        def method_lookup(val):
            return getattr(cls, '_' + val)
        parser.add_argument('method', type=method_lookup)
        parser.add_argument(
            '--host', type=models.ProcHostFilter,
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


def _parse_swarm_params(filter):
    query_tokens = filter.split('-')
    keys = 'app__name', 'config_name', 'proc_name'
    return {
        key: val
        for key, val in zip(keys, query_tokens)
        if not _has_regex(val)
    }


def _has_regex(string):
    return '.*' in string


def _get_swarms(args):
    params = _parse_swarm_params(args.filter)
    logging.info('Searching for swarms: %s', params)
    return models.Swarm.load_all(args.vr, params)


def _resolve_ingredients(vr, ingredients):
    if not ingredients:
        return ingredients
    return [models.Ingredient.by_id(vr, ing) if ing.isdigit() else
            models.Ingredient.by_name(vr, ing) for ing in ingredients]


def _assemble_ingredients(old_ingredients, add_ingredients,
                          remove_ingredients):
    new_ingredients = old_ingredients + [add for add in add_ingredients if
                                         add not in old_ingredients]
    new_ingredients = [new for new in new_ingredients if
                       new not in remove_ingredients]
    return new_ingredients


def merge_dicts(*dict_args):
    """
    Given any number of dicts, shallow copy and merge into a new dict,
    precedence goes to key value pairs in latter dicts.
    """
    result = {}
    for dictionary in dict_args:
        result.update(dictionary)
    return result


def handle_command_line():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--url',
        help="Velociraptor URL (defaults to https://deploy, resolved; "
        "override with VELOCIRAPTOR_URL)")
    parser.add_argument(
        '--username',
        help="Override the username used for authentication",
        default=os.environ.get('VELOCIRAPTOR_USERNAME'),
    )
    jaraco.logging.add_arguments(parser, default_level=logging.WARNING)
    cmdline.Command.add_subparsers(parser)
    args = parser.parse_args()
    jaraco.logging.setup(args, format='%(message)s')
    args.vr = models.Velociraptor(args.url, args.username)
    try:
        args.action.run(args)
    except AttributeError:
        parser.print_usage()
        parser.exit(1)


if __name__ == "__main__":
    handle_command_line()
