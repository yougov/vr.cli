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
import mechanize

session = requests.session()
username = getpass.getuser()
password = keyring.get_password('YOUGOV.LOCAL', username) or getpass.getpass()
vr_base = 'https://deploy.yougov.net'

class SwarmFilter(unicode):
	def matches(self, names):
		return (name for name in names if re.match(self, name))

def get_args():
	parser = argparse.ArgumentParser()
	parser.add_argument('filter', type=SwarmFilter)
	parser.add_argument('tag')
	return parser.parse_args()

def auth():
	resp = session.get(vr_base)
	if 'baton' in resp.text:
		resp = session.post(resp.url, data=dict(username=username,
			password=password))
	return resp

def get_swarms(home):
	swarm_pat = re.compile('<option value="(?P<path>/swarm/\d+/)">(?P<name>.*?)</option>')
	matches = swarm_pat.finditer(home.text)
	swarms = {match.group('name'): match.group('path') for match in matches}
	if not swarms:
		print("No swarms found at", home.url, file=sys.stderr)
		print("Response was", home.text, file=sys.stderr)
		raise SystemExit(1)
	return swarms

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

def adapt_resp(resp):
	stream = io.StringIO(resp.text)
	stream.geturl = lambda: resp.url
	return stream


def swarm(path, tag):
	url = urlparse.urljoin(vr_base, path)
	resp = session.get(url)
	forms = mechanize.ParseResponse(adapt_resp(resp), backwards_compat=False)
	f = forms[0]
	data = dict(f.click_pairs())
	data['tag'] = tag
	return session.post(url, data=data)

def reswarm():
	args = get_args()
	swarms = get_swarms(auth())
	matched_names = list(args.filter.matches(swarms))
	print("Matched", len(matched_names), "apps")
	pprint.pprint(matched_names)
	countdown("Reswarming in {} sec")
	[swarm(swarms[name], args.tag) for name in matched_names]

if __name__ == '__main__':
	reswarm()
