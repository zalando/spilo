#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

"""

import sys
import os
import inspect
from distutils.cmd import Command

import setuptools
from setuptools.command.test import test as TestCommand
from setuptools import setup

if sys.version_info < (3, 4, 0):
    sys.stderr.write('FATAL: STUPS Senza needs to be run with Python 3.4+\n')
    sys.exit(1)

__location__ = os.path.join(os.getcwd(), os.path.dirname(inspect.getfile(inspect.currentframe())))


def read_version(package):
    data = {}
    with open(os.path.join(package, '__init__.py'), 'r') as fd:
        exec(fd.read(), data)
    return data['__version__']

NAME = 'spilo'
MAIN_PACKAGE = 'spilo'
VERSION = read_version(MAIN_PACKAGE)
DESCRIPTION = 'Spilo command line client'
LICENSE = 'Apache License 2.0'
URL = 'https://github.com/zalando/spilo'
AUTHOR = 'Feike Steenbergen'
EMAIL = 'feike.steenbergen@zalando.de'
KEYWORDS = 'aws spilo PostgreSQL cluster tunnel connect'

COVERAGE_XML = True
COVERAGE_HTML = False
JUNIT_XML = True

# Add here all kinds of additional classifiers as defined under
# https://pypi.python.org/pypi?%3Aaction=list_classifiers
CLASSIFIERS = [
    'Development Status :: 4 - Beta',
    'Environment :: Console',
    'Intended Audience :: Developers',
    'Intended Audience :: System Administrators',
    'License :: OSI Approved :: Apache Software License',
    'Operating System :: POSIX :: Linux',
    'Programming Language :: Python',
    'Programming Language :: Python :: 3.4',
    'Programming Language :: Python :: Implementation :: CPython',
]

CONSOLE_SCRIPTS = ['spilo = spilo.spilo:cli']


class PyTest(TestCommand):

    user_options = [('cov=', None, 'Run coverage'), ('cov-xml=', None, 'Generate junit xml report'), ('cov-html=',
                    None, 'Generate junit html report'), ('junitxml=', None, 'Generate xml of test results')]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.cov = None
        self.cov_xml = False
        self.cov_html = False
        self.junitxml = None

    def finalize_options(self):
        TestCommand.finalize_options(self)
        if self.cov is not None:
            self.cov = ['--cov', self.cov, '--cov-report', 'term-missing']
            if self.cov_xml:
                self.cov.extend(['--cov-report', 'xml'])
            if self.cov_html:
                self.cov.extend(['--cov-report', 'html'])
        if self.junitxml is not None:
            self.junitxml = ['--junitxml', self.junitxml]

    def run_tests(self):
        try:
            import pytest
        except:
            raise RuntimeError('py.test is not installed, run: pip install pytest')
        params = {'args': self.test_args}
        if self.cov:
            params['args'] += self.cov
            params['plugins'] = ['cov']
        if self.junitxml:
            params['args'] += self.junitxml
        params['args'] += ['--doctest-modules', MAIN_PACKAGE, '-s', '-vv']
        errno = pytest.main(**params)
        sys.exit(errno)


def sphinx_builder():
    try:
        from sphinx.setup_command import BuildDoc
    except ImportError:

        class NoSphinx(Command):

            user_options = []

            def initialize_options(self):
                raise RuntimeError('Sphinx documentation is not installed, run: pip install sphinx')

        return NoSphinx

    class BuildSphinxDocs(BuildDoc):

        def run(self):
            if self.builder == 'doctest':
                import sphinx.ext.doctest as doctest
                # Capture the DocTestBuilder class in order to return the total
                # number of failures when exiting
                ref = capture_objs(doctest.DocTestBuilder)
                BuildDoc.run(self)
                errno = ref[-1].total_failures
                sys.exit(errno)
            else:
                BuildDoc.run(self)

    return BuildSphinxDocs


class ObjKeeper(type):

    instances = {}

    def __init__(cls, name, bases, dct):
        cls.instances[cls] = []

    def __call__(cls, *args, **kwargs):
        cls.instances[cls].append(super(ObjKeeper, cls).__call__(*args, **kwargs))
        return cls.instances[cls][-1]


def capture_objs(cls):
    from six import add_metaclass
    module = inspect.getmodule(cls)
    name = cls.__name__
    keeper_class = add_metaclass(ObjKeeper)(cls)
    setattr(module, name, keeper_class)
    cls = getattr(module, name)
    return keeper_class.instances[cls]


def get_install_requirements(path):
    content = open(os.path.join(__location__, path)).read()
    return [req for req in content.split('\\n') if req != '']


def read(fname):
    return open(os.path.join(__location__, fname)).read()


def setup_package():
    # Assemble additional setup commands
    cmdclass = {}
    cmdclass['docs'] = sphinx_builder()
    cmdclass['doctest'] = sphinx_builder()
    cmdclass['test'] = PyTest

    # Some helper variables
    version = os.getenv('GO_PIPELINE_LABEL', VERSION)

    docs_path = os.path.join(__location__, 'docs')
    docs_build_path = os.path.join(docs_path, '_build')
    install_reqs = get_install_requirements('requirements.txt')

    command_options = {'docs': {
        'project': ('setup.py', MAIN_PACKAGE),
        'version': ('setup.py', version.split('-', 1)[0]),
        'release': ('setup.py', version),
        'build_dir': ('setup.py', docs_build_path),
        'config_dir': ('setup.py', docs_path),
        'source_dir': ('setup.py', docs_path),
    }, 'doctest': {
        'project': ('setup.py', MAIN_PACKAGE),
        'version': ('setup.py', version.split('-', 1)[0]),
        'release': ('setup.py', version),
        'build_dir': ('setup.py', docs_build_path),
        'config_dir': ('setup.py', docs_path),
        'source_dir': ('setup.py', docs_path),
        'builder': ('setup.py', 'doctest'),
    }, 'test': {'test_suite': ('setup.py', 'tests'), 'cov': ('setup.py', MAIN_PACKAGE)}}
    if JUNIT_XML:
        command_options['test']['junitxml'] = 'setup.py', 'junit.xml'
    if COVERAGE_XML:
        command_options['test']['cov_xml'] = 'setup.py', True
    if COVERAGE_HTML:
        command_options['test']['cov_html'] = 'setup.py', True

    setup(
        name=NAME,
        version=version,
        url=URL,
        description=DESCRIPTION,
        author=AUTHOR,
        author_email=EMAIL,
        license=LICENSE,
        keywords=KEYWORDS,
        long_description=read('README.md'),
        classifiers=CLASSIFIERS,
        test_suite='tests',
        packages=setuptools.find_packages(exclude=['tests', 'tests.*']),
        install_requires=install_reqs,
        setup_requires=['flake8'],
        cmdclass=cmdclass,
        tests_require=['pytest-cov', 'pytest'],
        command_options=command_options,
        entry_points={'console_scripts': CONSOLE_SCRIPTS},
    )


if __name__ == '__main__':
    setup_package()
