from codecs import open
from os import path

from setuptools import find_packages, setup

here = path.abspath(path.dirname(__file__))


def get_long_description():
    with open(
        path.join(path.dirname(path.abspath(__file__)), "README.md"), encoding="utf8"
    ) as fp:
        return fp.read()


setup(
    name="lambda-pkg-resources",
    version="0.0.3",
    description="Supports a dist-info installation of packages with package exclusions",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    url="https://github.com/QuiNovas/lambda-pkg-resources",
    author="Joseph Wortmann",
    author_email="joseph.wortmann@gmail.com",
    license="APL 2.0",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3.8",
    ],
    keywords="pkg_resources extension",
    install_requires=["setuptools", "pip", "wheel"],
    package_dir={"": "src"},
    packages=find_packages("src"),
)
