#!/usr/bin/env python

# Project skeleton maintained at https://github.com/jaraco/skeleton

import io
import sys

import setuptools

with io.open('README.rst', encoding='utf-8') as readme:
    long_description = readme.read()

needs_wheel = {'release', 'bdist_wheel', 'dists'}.intersection(sys.argv)
wheel = ['wheel'] if needs_wheel else []

name = 'vr.cli'
description = 'Command-line client for Velociraptor'

setup_params = dict(
    name=name,
    use_scm_version=True,
    author="Jason R. Coombs",
    author_email="jaraco@jaraco.com",
    description=description or name,
    long_description=long_description,
    url="https://github.com/yougov/" + name,
    packages=setuptools.find_packages(),
    include_package_data=True,
    namespace_packages=name.split('.')[:-1],
    install_requires=[
        'jaraco.functools>=1.0,<2dev',
        'vr.common>=4.6.1',
        'more_itertools',
        'six',
        'datadiff>=1.1.6',
        'jaraco.ui>=1.2',
        'jaraco.timing',
        'jaraco.logging',
    ],
    extras_require={
    },
    setup_requires=[
        'setuptools_scm>=1.15.0',
    ] + wheel,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
    ],
    entry_points={
        'console_scripts': [
            'vr.cli = vr.cli:handle_command_line',
        ],
    },
)
if __name__ == '__main__':
    setuptools.setup(**setup_params)
