from __future__ import print_function

import argparse
import getpass
import re
import pprint
import urlparse
import io
import time
import sys
import datetime

import requests
import keyring
import lxml.html

session = requests.session()
username = getpass.getuser()
password = keyring.get_password('YOUGOV.LOCAL', username) or getpass.getpass()
vr_base = 'https://deploy.yougov.net'

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

def get_args():
	parser = argparse.ArgumentParser()
	parser.add_argument('filter', type=SwarmFilter)
	parser.add_argument('tag')
	parser.add_argument('-x', '--exclude', action=FilterExcludeAction)
	return parser.parse_args()

def auth():
	resp = session.get(vr_base)
	if 'baton' in resp.text:
		resp = session.post(resp.url, data=dict(username=username,
			password=password))
	return resp

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
		url = urlparse.urljoin(vr_base, self.path)
		resp = session.get(url)
		page = lxml.html.fromstring(resp.text, base_url=resp.url)
		form = page.forms[0]
		if tag:
			form.fields.update(tag=tag)
		return lxml.html.submit_form(form,
			open_http=get_lxml_opener(session))

	def load_meta(self):
		url = urlparse.urljoin(vr_base, self.path)
		resp = session.get(url)
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

def get_lxml_opener(session):
	"""
	Given a requests session, return an opener suitable for passing to LXML
	"""
	return lambda method, url, values: session.request(url=url, method=method,
		data=dict(values))

def reswarm():
	args = get_args()
	swarms = Swarm.load_all(auth())
	matched = list(args.filter.matches(swarms))
	print("Matched", len(matched), "apps")
	pprint.pprint(matched)
	countdown("Reswarming in {} sec")
	[swarm.reswarm(args.tag) for swarm in matched]

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

def rebuild(app, tag):
	url = urlparse.urljoin(vr_base, '/build/')
	resp = session.get(url)
	page = lxml.html.fromstring(resp.text, base_url=resp.url)
	form = page.forms[0]
	app_lookup = select_lookup(form.inputs['app_id'])
	form.fields.update(app_id=app_lookup[app])
	form.fields.update(tag=tag)
	return lxml.html.submit_form(form, open_http=get_lxml_opener(session))

class hashabledict(dict):
	def __hash__(self):
		return hash(tuple(sorted(self.items())))

def unique_builds(swarms):
	items = [
		hashabledict(swarm.build)
		for swarm in swarms
	]
	return set(items)

def release(swarm):
	url = urlparse.urljoin(vr_base, '/release/')
	resp = session.get(url)
	page = lxml.html.fromstring(resp.text, base_url=resp.url)
	form = page.forms[0]
	build_lookup = first_match_lookup(form.inputs['build_id'])
	recipe_lookup = select_lookup(form.inputs['recipe_id'])
	build = '-'.join([swarm.app, swarm.tag])
	form.fields.update(build_id=build_lookup[build])
	recipe = '-'.join([swarm.app, swarm.recipe])
	form.fields.update(recipe_id=recipe_lookup[recipe])
	return lxml.html.submit_form(form, open_http=get_lxml_opener(session))

def rebuild_all():
	args = get_args()
	swarms = Swarm.load_all(auth())
	swarms = list(args.filter.matches(swarms))
	print("Matched", len(swarms), "apps")
	pprint.pprint(swarms)
	print('loading swarm metadata...')
	for swarm in swarms:
		swarm.load_meta()
	countdown("Rebuilding in {} sec")
	for build in unique_builds(swarms):
		rebuild(**build)

	raw_input("Hit enter to continue once builds are done...")
	for swarm in swarms:
		release(swarm)

	print('swarming new releases...')
	for swarm in swarms:
		swarm.reswarm()

if __name__ == '__main__':
	reswarm()
	#rebuild_all()
