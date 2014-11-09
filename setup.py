import sys

from setuptools import find_packages, setup


backports = []
if sys.version_info < (3, 4):
    backports.append('enum34')


setup(
    name='flax',
    version='0.1',
    description='A roguelike',
    # long_description=...
    author='Eevee',
    author_email='eevee.flax@veekun.com',
    url='https://github.com/eevee/flax',
    license='MIT',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python',
        'Topic :: Games/Entertainment',
    ],

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
