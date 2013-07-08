from __future__ import print_function

from __future__ import print_function

import pprint
import argparse
import itertools

import six
import lxml.html
from jaraco.util import cmdline

from . import swarms as models


class FilterExcludeAction(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		namespace.filter.exclusions.append(values)

class Swarm(cmdline.Command):
	@classmethod
	def add_arguments(cls, parser):
		parser.add_argument('filter', type=models.SwarmFilter)
		parser.add_argument('tag')
		parser.add_argument('-x', '--exclude', action=FilterExcludeAction)

	@classmethod
	def run(cls, args):
		swarms = models.Swarm.load_all(models.Velociraptor.auth())
		matched = list(args.filter.matches(swarms))
		print("Matched", len(matched), "apps")
		pprint.pprint(matched)
		models.countdown("Reswarming in {} sec")
		[swarm.reswarm(args.tag) for swarm in matched]


class Builder(object):
	@classmethod
	def build(cls, app, tag):
		resp = models.Velociraptor.load('/build/')
		page = lxml.html.fromstring(resp.text, base_url=resp.url)
		form = page.forms[0]
		app_lookup = models.select_lookup(form.inputs['app_id'])
		form.fields.update(app_id=app_lookup[app])
		form.fields.update(tag=tag)
		return models.Velociraptor.submit(form)


class Build(Builder, cmdline.Command):
	@classmethod
	def add_arguments(cls, parser):
		parser.add_argument('app')
		parser.add_argument('tag')

	@classmethod
	def run(cls, args):
		models.Velociraptor.auth()
		cls.build(args.app, args.tag)


class RebuildAll(Builder, cmdline.Command):
	@classmethod
	def add_arguments(cls, parser):
		parser.add_argument('filter', type=models.SwarmFilter)
		parser.add_argument('-x', '--exclude', action=FilterExcludeAction)

	@classmethod
	def run(cls, args):
		swarms = models.Swarm.load_all(models.Velociraptor.auth())
		swarms = list(args.filter.matches(swarms))
		print("Matched", len(swarms), "apps")
		pprint.pprint(swarms)
		print('loading swarm metadata...')
		for swarm in swarms:
			swarm.load_meta()
		models.countdown("Rebuilding in {} sec")
		for build in cls.unique_builds(swarms):
			cls.build(**build)

		six.moves.input("Hit enter to continue once builds are done...")
		for swarm in swarms:
			cls.release(swarm)

		print('swarming new releases...')
		for swarm in swarms:
			swarm.reswarm()

	@classmethod
	def unique_builds(cls, swarms):
		items = [
			models.HashableDict(swarm.build)
			for swarm in swarms
		]
		return set(items)

	@classmethod
	def release(cls, swarm):
		resp = models.Velociraptor.load('/release/')
		page = lxml.html.fromstring(resp.text, base_url=resp.url)
		form = page.forms[0]
		build_lookup = models.first_match_lookup(form.inputs['build_id'])
		recipe_lookup = models.select_lookup(form.inputs['recipe_id'])
		build = '-'.join([swarm.app, swarm.tag])
		form.fields.update(build_id=build_lookup[build])
		recipe = '-'.join([swarm.app, swarm.recipe])
		form.fields.update(recipe_id=recipe_lookup[recipe])
		return models.Velociraptor.submit(form)


class ListProcs(cmdline.Command):

	@classmethod
	def add_arguments(cls, parser):
		parser.add_argument('filter', type=models.SwarmFilter)

	@classmethod
	def run(cls, args):
		swarmtmpl = '{} [{}]'
		proctmpl = '  {host:<22}  {port:<5}  {statename:<9}  {description}'

		all_swarms = models.Swarm.load_all(models.Velociraptor.auth())
		swarm_names = [s.name for s in args.filter.matches(all_swarms)]

		our_procs = [
			p for p in models.Velociraptor.procs()
			if p['swarmname'] in swarm_names
		]

		kfunc = lambda proc: (proc['swarmname'], proc['tag'])
		our_procs = sorted(our_procs, key=kfunc)
		proc_groups = itertools.groupby(our_procs, key=kfunc)

		for ktpl, procs in proc_groups:
			print()
			print (swarmtmpl.format(*ktpl))
			for proc in procs:
				print (proctmpl.format(**proc))

class ListSwarms(cmdline.Command):

	@classmethod
	def add_arguments(cls, parser):
		parser.add_argument('filter', type=models.SwarmFilter, nargs='?')

	@classmethod
	def run(cls, args):
		all_swarms = models.Swarm.load_all(models.Velociraptor.auth())
		filtered_swarms = all_swarms
		if args.filter:
			filtered_swarms = args.filter.matches(all_swarms)
		swarm_names = [s.name for s in filtered_swarms]
		[print(name) for name in sorted(swarm_names)]


def handle_command_line():
	parser = argparse.ArgumentParser()
	parser.add_argument('--url',
		help="Velociraptor URL (defaults to https://deploy, resolved)")
	parser.add_argument('--username',
		help="Override the username used for authentication")
	cmdline.Command.add_subparsers(parser)
	args = parser.parse_args()
	if args.url:
		models.Velociraptor.base = args.url
	models.Velociraptor.username = args.username
	args.action.run(args)
