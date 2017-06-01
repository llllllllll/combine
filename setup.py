#!/usr/bin/env python
from setuptools import setup, find_packages
import sys

long_description = ''

if 'upload' in sys.argv:
    with open('README.rst') as f:
        long_description = f.read()


setup(
    name='combine',
    version='0.1.0',
    description='Farm that PP!',
    author='Joe Jevnik',
    author_email='joejev@gmail.com',
    packages=find_packages(),
    long_description=long_description,
    license='GPLv3+',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',  # noqa
        'Natural Language :: English',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3 :: Only',
        'Topic :: Games/Entertainment',
    ],
    url='https://github.com/llllllllll/combine',
)
