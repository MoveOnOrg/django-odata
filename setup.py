from setuptools import setup
import textwrap

import sys
if sys.version_info < (3,0):
    sys.exit('Sorry, Python < 3 is not supported')

setup(
    name='django-odata',
    version='0.1',
    author='MoveOn.org',
    author_email='opensource@moveon.org',
    py_modules=['odata'],
    url='https://github.com/MoveOnOrg/django-odata',
    license='MIT',
    description="odata filter adapter for django -- incomplete, but does the basic stuff",
    long_description=textwrap.dedent(open('README.md', 'r').read()),
    install_requires=[
        'parsimonious==0.7.0',
    ],
    keywords = "python django odata",
    classifiers=['Intended Audience :: Developers', 'Operating System :: OS Independent', 'Topic :: Internet :: WWW/HTTP'],
)
