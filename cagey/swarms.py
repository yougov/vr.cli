from __future__ import print_function

import argparse
import getpass
import re
import pprint
import urlparse
import time
import sys
import datetime
import socket
import os
import collections

import requests
import lxml.html
import jaraco.util.functools
from jaraco.util import cmdline

try:
	import keyring
except ImportError:
	# stub out keyring
	class keyring:
		def get_password(*args, **kwargs):
			return None

Credential = collections.namedtuple('Credential', 'username password')

@jaraco.util.functools.once
def get_credentials():
	username = getpass.getuser()
	password = keyring.get_password('YOUGOV.LOCAL', username)
	if password is None:
		password = getpass.getpass("Password for {username}>".format(
			username=username))
	return Credential(username, password)

class HashableDict(dict):
	def __hash__(self):
		return hash(tuple(sorted(self.items())))


class SwarmFilter(unicode):
	"""
	A regular expression indicating which swarm names to include.
	"""
	exclusions = []
	"additional patterns to exclude"

	def matches(self, swarms):
		return filter(self.match, swarms)

	def match(self, swarm):
		return (
			not any(re.search(exclude, swarm.name, re.I)
				for exclude in self.exclusions)
			and re.match(self, swarm.name)
		)

class FilterExcludeAction(argparse.Action):
	def __call__(self, parser, namespace, values, option_string=None):
		namespace.filter.exclusions.append(values)

class Velociraptor(object):
	def _get_base():
		"""
		if 'deploy' resolves in your environment, use the hostname for which
		that name resolves.
		Override with 'VELOCIRAPTOR_URL'
		"""
		try:
			name, aliaslist, addresslist = socket.gethostbyname_ex('deploy')
		except socket.gaierror:
			name = 'deploy'
		fallback = 'https://{name}/'.format(name=name)
		return os.environ.get('VELOCIRAPTOR_URL', fallback)

	base = _get_base()
	session = requests.session()

	@classmethod
	def auth(cls):
		"""
		Authenticate to Velociraptor and return the home page
		"""
		cred = get_credentials()
		print("Authenticating to {base} as {username}".format(
			base=cls.base,
			username=cred.username,
		))
		resp = cls.session.get(cls.base)
		if 'baton' in resp.text:
			resp = cls.session.post(resp.url, data=cred._asdict())
		return resp

	@classmethod
	def load(cls, path):
		url = urlparse.urljoin(cls.base, path)
		return cls.session.get(url)

	@classmethod
	def open_for_lxml(cls, method, url, values):
		"""
		Open a request for lxml using the class' session
		"""
		return cls.session.request(url=url, method=method, data=dict(values))

	@classmethod
	def submit(cls, form):
		return lxml.html.submit_form(form, open_http=cls.open_for_lxml)

class Swarm(object):
	"""
	A VR Swarm
	"""
	def __init__(self, name, path, **kwargs):
		self.name = name
		self.path = path
		self.__dict__.update(kwargs)

	def __repr__(self):
		return self.name

	@classmethod
	def load_all(cls, home):
		"""
		Load all swarms as found on the VR homepage
		"""
		swarm_pat = re.compile('<option value="(?P<path>/swarm/\d+/)">(?P<name>.*?)</option>')
		matches = swarm_pat.finditer(home.text)
		swarms = [Swarm(**match.groupdict()) for match in matches]
		if not swarms:
			print("No swarms found at", home.url, file=sys.stderr)
			print("Response was", home.text, file=sys.stderr)
			raise SystemExit(1)
		return swarms

	def reswarm(self, tag=None):
		resp = Velociraptor.load(self.path)
		page = lxml.html.fromstring(resp.text, base_url=resp.url)
		form = page.forms[0]
		if tag:
			form.fields.update(tag=tag)
		return Velociraptor.submit(form)

	def load_meta(self):
		resp = Velociraptor.load(self.path)
		page = lxml.html.fromstring(resp.text, base_url=resp.url)
		form = page.forms[0]
		app, recipe, proc = self.name.split('-')
		self.__dict__.update(form.fields)

	@property
	def app(self):
		app, recipe, proc = self.name.split('-')
		return app

	@property
	def recipe(self):
		app, recipe, proc = self.name.split('-')
		return recipe

	@property
	def build(self):
		return {'app': self.app, 'tag': self.tag}

def countdown(template):
	now = datetime.datetime.now()
	delay = datetime.timedelta(seconds=5)
	deadline = now + delay
	remaining = deadline - datetime.datetime.now()
	while remaining:
		remaining = deadline - datetime.datetime.now()
		remaining = max(datetime.timedelta(), remaining)
		msg = template.format(remaining.total_seconds())
		print(msg, end=' '*10)
		sys.stdout.flush()
		time.sleep(.1)
		print('\b'*80, end='')
		sys.stdout.flush()
	print()


def select_lookup(element):
	"""
	Given an LXML 'select' element, return a dict of Option text -> value
	"""
	return dict(zip(element.itertext('option'), element.value_options))

def first_match_lookup(element):
	"""
	Like select_lookup except if there are multiple options with the same
	string, prefer the first.
	"""
	return dict(
		zip(
			reversed(list(element.itertext('option'))),
			reversed(element.value_options),
		))


class Reswarm(cmdline.Command):
	@classmethod
	def add_arguments(cls, parser):
		parser.add_argument('filter', type=SwarmFilter)
		parser.add_argument('tag')
		parser.add_argument('-x', '--exclude', action=FilterExcludeAction)

	@classmethod
	def run(cls, args):
		swarms = Swarm.load_all(Velociraptor.auth())
		matched = list(args.filter.matches(swarms))
		print("Matched", len(matched), "apps")
		pprint.pprint(matched)
		countdown("Reswarming in {} sec")
		[swarm.reswarm(args.tag) for swarm in matched]


class RebuildAll(cmdline.Command):
	@classmethod
	def add_arguments(cls, parser):
		parser.add_argument('filter', type=SwarmFilter)
		parser.add_argument('-x', '--exclude', action=FilterExcludeAction)

	@classmethod
	def run(cls, args):
		swarms = Swarm.load_all(Velociraptor.auth())
		swarms = list(args.filter.matches(swarms))
		print("Matched", len(swarms), "apps")
		pprint.pprint(swarms)
		print('loading swarm metadata...')
		for swarm in swarms:
			swarm.load_meta()
		countdown("Rebuilding in {} sec")
		for build in cls.unique_builds(swarms):
			cls.rebuild(**build)

		raw_input("Hit enter to continue once builds are done...")
		for swarm in swarms:
			cls.release(swarm)

		print('swarming new releases...')
		for swarm in swarms:
			swarm.reswarm()

	@classmethod
	def rebuild(cls, app, tag):
		resp = Velociraptor.load('/build/')
		page = lxml.html.fromstring(resp.text, base_url=resp.url)
		form = page.forms[0]
		app_lookup = select_lookup(form.inputs['app_id'])
		form.fields.update(app_id=app_lookup[app])
		form.fields.update(tag=tag)
		return Velociraptor.submit(form)

	@classmethod
	def unique_builds(cls, swarms):
		items = [
			HashableDict(swarm.build)
			for swarm in swarms
		]
		return set(items)

	@classmethod
	def release(cls, swarm):
		resp = Velociraptor.load('/release/')
		page = lxml.html.fromstring(resp.text, base_url=resp.url)
		form = page.forms[0]
		build_lookup = first_match_lookup(form.inputs['build_id'])
		recipe_lookup = select_lookup(form.inputs['recipe_id'])
		build = '-'.join([swarm.app, swarm.tag])
		form.fields.update(build_id=build_lookup[build])
		recipe = '-'.join([swarm.app, swarm.recipe])
		form.fields.update(recipe_id=recipe_lookup[recipe])
		return Velociraptor.submit(form)


def handle_command_line():
	parser = argparse.ArgumentParser()
	parser.add_argument('--url',
		help="Velociraptor URL (defaults to https://deploy, resolved)")
	cmdline.Command.add_subparsers(parser)
	args = parser.parse_args()
	if args.url:
		Velociraptor.base = args.url
	args.action.run(args)

if __name__ == '__main__':
	handle_command_line()
