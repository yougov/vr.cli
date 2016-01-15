import argparse
import importlib

from jaraco.ui import cmdline


def test_commands():
	"Ensure the commands are registered"
	importlib.import_module('vr.cli')
	parser = argparse.ArgumentParser()
	cmdline.Command.add_subparsers(parser)
	help_action, subparsers_action = parser._subparsers._actions
	subcommand_names = set(subparsers_action.choices)
	assert subcommand_names > {'build', 'swarm', 'compare-releases'}
