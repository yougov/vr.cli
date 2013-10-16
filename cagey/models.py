from __future__ import print_function

import getpass
import re
import time
import sys
import datetime
import socket
import os
import collections
import logging

import six
import requests
import lxml.html
import jaraco.util.functools

try:
	import keyring
except ImportError:
	# stub out keyring
	class keyring:
		@staticmethod
		def get_password(*args, **kwargs):
			return None

log = logging.getLogger(__name__)

Credential = collections.namedtuple('Credential', 'username password')

class HashableDict(dict):
	def __hash__(self):
		return hash(tuple(sorted(self.items())))


class SwarmFilter(six.text_type):
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

class Velociraptor(object):
	uptest_url = '/api/uptest/latest'

	def __init__(self, base=None, username=None):
		self.base = base or self._get_base()
		self.username = username
		self.home = self.auth()

	@classmethod
	def viable(cls, base=None):
		"""
		Is this class viable for the given base?
		"""
		try:
			cls(base).load(cls.uptest_url)
			return True
		except Exception:
			return False

	@staticmethod
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

	@classmethod
	def hostname(cls):
		return six.moves.urllib.parse.urlparse(cls.base).hostname

	base = _get_base.__func__()
	session = requests.session()
	username = None

	@jaraco.util.functools.once
	def get_credentials(self):
		username = self.username or getpass.getuser()
		password = keyring.get_password('YOUGOV.LOCAL', username)
		if password is None:
			password = getpass.getpass("{username}@{hostname}'s password: ".format(
				username=username, hostname=self.hostname()))
		return Credential(username, password)

	def auth(self):
		"""
		Authenticate to Velociraptor and return the home page
		"""
		cred = self.get_credentials()
		print("Authenticating to {base} as {username}".format(
			base=self.base,
			username=cred.username,
		))
		resp = self.session.get(self.base)
		if 'baton' in resp.text:
			resp = self.session.post(resp.url, data=cred._asdict())
		return resp

	@classmethod
	def load(cls, path):
		url = six.moves.urllib.parse.urljoin(cls.base, path)
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

	@classmethod
	def hosts(cls):
		page = cls.load('/api/hosts/')
		for hostname in page.json()['hosts']:
			yield hostname

	@classmethod
	def procs(cls):
		for hostname in cls.hosts():
			ppage = cls.load('/api/hosts/%s/procs' % hostname)
			for proc in ppage.json()['procs']:
				swarmname = '{app}-{recipe}-{proc}'.format(**proc)
				proc['swarmname'] = swarmname
				yield proc

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

	def reswarm(self, vr, tag=None):
		resp = vr.load(self.path)
		page = lxml.html.fromstring(resp.text, base_url=resp.url)
		form = page.forms[0]
		if tag:
			form.fields.update(tag=tag)
		return vr.submit(form)

	def load_meta(self, vr):
		resp = vr.load(self.path)
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