from setuptools import setup
desc = '''bcib:
'''
setup(
    name="bcib",
    version="0.0.0",
    author="Pierre Schnizer",
    author_email="pierre.schnizer@helmholtz-berlin.de",
    description=desc,
    license="GPL",
    keywords="callback, iterator",
    url="https://github.com/hz-b/naus",
    packages=['bcib'],
    extra_requires={"bluesky": ["bluesky"]},
    classifiers=[
        "Development Status :: 2 - Pre - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: GNU General Public License (GPL)",
        "Programming Language :: Python :: 3",
        "Topic :: Scientific/Engineering",
    ]
)
