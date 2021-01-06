# lambda-pkg-resources

#### An extension to `pkg_resources` that provides for dist-info (standard `whl`) installation of packages and for exclusion of unwanted or unnecessary packages

The AWS Lambda execution environment inherently provides a number of Python packages, with the two most important of these being `boto3` and `botocore`. The combination of these (and their dependencies) are several MB of package storage.

Many of the Python open-source packages built to work with AWS `install_requires` the `boto3` package. While this is appropriate for non-Lamdba usage, it presents two problems when used in a Lambda function.

The first problem is bloat of the Lambda function package, leading to longer cold-start times and an inability to use the Lambda console to manage the code in the function.

The second problem is that the version of `boto3` included in the Lambda package necessarily "drifts" from the version of the AWS API that it is attempting to call. This can lead to strange errors where the Lambda function starts throwing strange errors or simply failing to execute appropriately (sometimes with no exceptions thrown).

This library allows for the programatic creation of Lambda funciton and layer packages that install what is required for the function/layer to run while excluding, anywhere within the dependency tree, the Python packages that are already provided by the AWS Lambda execution environment. It can additionally be used programatically to exclude packages in other execution environments if desired.

This library provides three components that work in conjunction with the standard `pkg_resources` Python package to perform a dist-info install of dependent packages and allow for exclusion of packages that are not desired.

---

**LAMBDA_EXCLUDES**

A global variable that is a `set` of the current package names provided by the AWS Lambda execution environment.

---

**ExcludesWorkingSet**

Extends `WorkingSet` and performs a dist-info install of packages via the overridden `resolve` method.

---

**DistInstaller**

An installer to that can be used in the `resolve` method of either `WorkingSet` or `ExcludesWorkingSet` through the use of the `fetch_dist` method.

---

### Example Usage

``` python
from lambda_pkg_resources import DistInstaller, ExcludesWorkingSet, LAMBDA_EXCLUDES
from pkg_resources import parse_requirements

ws = ExcludesWorkingSet(
    entries=["package/install/directory"],
    excludes={"six"},
)
di = DistInstaller("package/install/directory")
ws.resolve(
    parse_requirements(["watchtower", "python-jose"]), installer=di.fetch_dist, replace_conflicting=True
)

```
This will install `watchtower` and `python-jose` in "packages/install/directory", excluding the package `six` anywhere it is found in the dependency tree.

---

This package is used in [`lambda-setuptools`](https://github.com/QuiNovas/lambda-setuptools) to remove all of the libraries listed in `LAMBDA_EXCLUDES` from the
built package or library using the `ldist` command.
