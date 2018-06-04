#!/usr/bin/env python

# Project skeleton maintained at https://github.com/jaraco/skeleton

import io

import setuptools

with io.open('README.rst', encoding='utf-8') as readme:
    long_description = readme.read()

name = 'vr.cli'
description = 'Command-line client for Velociraptor'
nspkg_technique = 'managed'
"""
Does this package use "native" namespace packages or
pkg_resources "managed" namespace packages?
"""

params = dict(
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
    python_requires='>=3.5',
    install_requires=[
        'jaraco.functools>=1.0,<2dev',
        'vr.common>=5.4',
        'more_itertools',
        'six',
        'datadiff>=1.1.6',
        'jaraco.ui>=1.2',
        'jaraco.timing',
        'jaraco.logging',
    ],
    extras_require={
        'testing': [
            # upstream
            'pytest>=3.5',
            'pytest-sugar>=0.9.1',
            'collective.checkdocs',
            'pytest-flake8',

            # local
        ],
        'docs': [
            # upstream
            'sphinx',
            'jaraco.packaging>=3.2',
            'rst.linker>=1.9',

            # local
        ],
    },
    setup_requires=[
        'setuptools_scm>=1.15.0',
    ],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
    ],
    entry_points={
        'console_scripts': [
            'vr.cli = vr.cli:handle_command_line',
        ],
    },
)
if __name__ == '__main__':
    setuptools.setup(**params)
