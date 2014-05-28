from __future__ import print_function

import pprint
import argparse

from jaraco.util import cmdline
from jaraco.util import ui

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
		[swarm.dispatch(version=args.tag) for swarm in matched]


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


class ListProcs(cmdline.Command):

	@classmethod
	def add_arguments(cls, parser):
		parser.add_argument('filter', type=models.SwarmFilter)

	@classmethod
	def run(cls, args):
		swarmtmpl = '{swarm.name} [{swarm.version}]'
		proctmpl = '  {host:<22}  {port:<5}  {statename:<9}  {description}'

		all_swarms = models.Swarm.load_all(args.vr)
		swarms = args.filter.matches(all_swarms)

		for swarm in swarms:
			print()
			print(swarmtmpl.format(**vars()))
			for proc in swarm.procs:
				print(proctmpl.format(**proc))

class ListSwarms(cmdline.Command):

	@classmethod
	def add_arguments(cls, parser):
		parser.add_argument('filter', type=models.SwarmFilter, nargs='?')

	@classmethod
	def run(cls, args):
		all_swarms = models.Swarm.load_all(args.vr)
		filtered_swarms = all_swarms
		if args.filter:
			filtered_swarms = args.filter.matches(all_swarms)
		[print(swarm) for swarm in sorted(filtered_swarms)]


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
