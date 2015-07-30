from setuptools import setup

setup(
    name='spilo',
    version='0.1',
    py_modules=['spilo'],
    install_requires=[
        'Click',
    ],
    entry_points='''
        [console_scripts]
        spilo=spilo:cli
    ''',
)
