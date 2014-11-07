import sys

from setuptools import find_packages, setup


backports = []
if sys.version_info < (3, 4):
    backports.append('enum34')


setup(
    name='flax',
    version='0.0',
    description='A roguelike.',
    #long_description=...
    author='Eevee',
    author_email='eevee.flax@veekun.com',
    license='MIT',

    # TODO classifiers and keywords before trying to upload

    packages=find_packages(),
    install_requires=backports + [
        'urwid',
        'zope.interface',
    ],

    entry_points={
        'console_scripts': [
            'flax = flax.ui.console:main',
        ],
    },
)
