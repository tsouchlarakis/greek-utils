#!/usr/bin/env python

from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('CHANGELOG.rst') as changelog_file:
    changelog = changelog_file.read()

with open('requirements.in') as requirements_file:
    requirements = requirements_file.read().split()

test_requirements = ['pytest>=3', ]

setup(
    author='Andoni Sooklaris',
    author_email='andoni.sooklaris@gmail.com',
    python_requires='>=3.6',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ],
    description="Programmable interface to Cooljugator's Modern Greek verb database.",
    entry_points={
        'console_scripts': [
            'greek-utils=greek_utils.cli:main',
        ],
    },
    install_requires=requirements,
    license='MIT license',
    # long_description=readme + '\n\n' + changelog,
    include_package_data=True,
    keywords='greek_utils',
    name='greek_utils',
    packages=find_packages(include=['greek_utils', 'greek_utils.*']),
    test_suite='tests',
    tests_require=test_requirements,
    url='https://github.com/tsouchlarakis/greek-utils',
    version='0.1.0',
    zip_safe=False,
)
