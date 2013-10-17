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
import copy
import json
import functools

import six
import requests
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
		self.session.auth = self.get_credentials()

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
	session.headers = {
		'Content-Type': 'application/json',
	}
	username = None

	@jaraco.util.functools.once
	def get_credentials(self):
		username = self.username or getpass.getuser()
		password = keyring.get_password('YOUGOV.LOCAL', username)
		if password is None:
			password = getpass.getpass("{username}@{hostname}'s password: ".format(
				username=username, hostname=self.hostname()))
		return Credential(username, password)

	def load(self, path):
		url = self._build_url(path)
		url += '?format=json&limit=9999'
		return self.session.get(url).json()

	def cut(self, build, **kwargs):
		"""
		Cut a release
		"""
		raise NotImplementedError("Can't cut releases (config?)")

	def _build_url(self, *parts):
		joiner = six.moves.urllib.parse.urljoin
		return functools.reduce(joiner, parts, self.base)


class Swarm(object):
	"""
	A VR Swarm
	"""
	def __init__(self, vr, obj):
		self._vr = vr
		self.__dict__.update(obj)

	def __lt__(self, other):
		return self.name < other.name

	@property
	def name(self):
		return '-'.join([self.app_name, self.config_name, self.proc_name])

	def __repr__(self):
		return self.name

	@classmethod
	def load_all(cls, vr):
		"""
		Load all swarms
		"""
		swarm_obs = vr.load('/api/v1/swarms/')['objects']
		swarms = [cls(vr, ob) for ob in swarm_obs]
		return swarms

	def dispatch(self, **changes):
		"""
		Patch the swarm with changes and then trigger the swarm.
		"""
		self.patch(**changes)
		trigger_url = self._vr._build_url(self.resource_uri, 'swarm/')
		resp = self._vr.session.post(trigger_url)
		resp.raise_for_status()

	def patch(self, **changes):
		if not changes:
			return
		url = self._vr._build_url(self.resource_uri)
		resp = self._vr.session.patch(url, json.dumps(changes))
		resp.raise_for_status()
		self.__dict__.update(changes)

	def save(self):
		url = self._vr._build_url(self.resource_uri)
		content = copy.deepcopy(self.__dict__)
		content.pop('_vr')
		resp = self._vr.session.put(url, json.dumps(content))
		resp.raise_for_status()

	@property
	def app(self):
		return self.app_name

	@property
	def recipe(self):
		return self.config_name

	def new_build(self):
		return Build._for_app_and_tag(
			self._vr,
			self.app,
			self.version,
		)


class Build(object):
	base = '/api/v1/builds/'

	def __init__(self, vr, obj):
		self._vr = vr
		self.__dict__.update(obj)

	@property
	def created(self):
		return 'id' in vars(self)

	def create(self):
		if self.created:
			raise ValueError("Build already created")
		doc = copy.deepcopy(self.__dict__)
		doc.pop('_vr')
		url = self._vr._build_url(self.base)
		resp = self._vr.session.post(url, json.dumps(doc))
		resp.raise_for_status()
		self.load(resp.headers['location'])

	def load(self, url):
		resp = self._vr.session.get(url)
		resp.raise_for_status()
		self.__dict__.update(resp.json())

	def assemble(self):
		"""
		Assemble a build
		"""
		if not self.created:
			self.create()
		# trigger the build
		url = self._vr._build_url(self.resource_uri, 'build/')
		resp = self._vr.session.post(url)
		resp.raise_for_status()

	@classmethod
	def _for_app_and_tag(cls, vr, app, tag):
		obj = dict(app='/api/v1/apps/' + app + '/', tag=tag)
		return cls(vr, obj)

	def __hash__(self):
		hd = HashableDict(self.__dict__)
		hd.pop('_vr')
		return hash(hd)

	def __eq__(self, other):
		return vars(self) == vars(other)

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
