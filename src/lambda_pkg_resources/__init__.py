from collections import defaultdict
from concurrent.futures.thread import ThreadPoolExecutor
from fnmatch import translate
from glob import glob
from os import environ, listdir, path
from re import IGNORECASE
from re import compile as re_compile
from re import match
from subprocess import check_call
from sys import executable
from tempfile import TemporaryDirectory
from threading import Lock
from typing import AbstractSet, Callable, List, Optional, Sequence
from zipfile import ZipFile

from pkg_resources import (
    BINARY_DIST,
    Distribution,
    DistributionNotFound,
    Environment,
    PathMetadata,
    Requirement,
    VersionConflict,
    WorkingSet,
    _ReqExtras,
    find_distributions,
    get_distribution,
    safe_name,
)

__all__ = ["ExcludesWorkingSet", "DistInstaller", "LAMBDA_EXCLUDES"]


LAMBDA_EXCLUDES = {
    "boto3",
    "botocore",
    "jmespath",
    "pip",
    "python-dateutil",
    "rapid-client",
    "s3transfer",
    "setuptools",
    "six",
    "urllib3",
}


class ExcludesWorkingSet(WorkingSet):
    def __init__(
        self,
        entries: Optional[Sequence[str]] = None,
        excludes: Optional[AbstractSet[str]] = None,
    ) -> None:
        self.excludes = {safe_name(exclude).lower() for exclude in (excludes or set())}
        super().__init__(entries=entries)

    def resolve(
        self,
        requirements: Sequence[Requirement],
        env: Optional[Environment] = None,
        installer: Optional[Callable[[str], Distribution]] = None,
        replace_conflicting: Optional[bool] = False,
        extras: List[str] = None,
    ) -> List[Distribution]:
        """List all distributions needed to (recursively) meet `requirements`
        `requirements` must be a sequence of ``Requirement`` objects.  `env`,
        if supplied, should be an ``Environment`` instance.  If
        not supplied, it defaults to all distributions available within any
        entry or distribution in the working set.  `installer`, if supplied,
        will be invoked with each requirement that cannot be met by an
        already-installed distribution; it should return a ``Distribution`` or
        ``None``.
        Unless `replace_conflicting=True`, raises a VersionConflict exception
        if
        any requirements are found on the path that have the correct name but
        the wrong version.  Otherwise, if an `installer` is supplied it will be
        invoked to obtain the correct version of the requirement and activate
        it.
        `extras` is a list of the extras to be used with these requirements.
        This is important because extra requirements may look like `my_req;
        extra = "my_extra"`, which would otherwise be interpreted as a purely
        optional requirement.  Instead, we want to be able to assert that these
        requirements are truly required.
        """

        # set of processed requirements
        processed = {}
        # key -> dist
        best = {}
        resolved = []

        requirement_extras = _ReqExtras()

        # Mapping of requirement to set of distributions that required it;
        # useful for reporting info about conflicts.
        required_by = defaultdict(set)

        # Use a collection to hold the env
        env: List[Environment] = [env]

        # The following function is use din mutliple threads
        # provide a lock
        lock = Lock()

        # set up the stack
        req_stack = list(requirements)[::-1]

        def resolve_requirement(requirement: Requirement):
            dist = best.get(requirement.key)
            if dist is None:
                # Find the best distribution and add it to the map
                dist = self.by_key.get(requirement.key)
                if dist is None or (dist not in requirement and replace_conflicting):
                    ws = self
                    with lock:
                        if env[0] is None:
                            if dist is None:
                                env[0] = Environment(self.entries)
                            else:
                                # Use an empty environment and workingset to avoid
                                # any further conflicts with the conflicting
                                # distribution
                                env[0] = Environment([])
                                ws = WorkingSet([])
                    dist = best[requirement.key] = env[0].best_match(
                        requirement,
                        ws,
                        installer,
                        replace_conflicting=replace_conflicting,
                    )
                    if dist is None:
                        requirers = required_by.get(requirement, None)
                        raise DistributionNotFound(requirement, requirers)
                resolved.append(dist)

            if dist not in requirement:
                # Oops, the "best" so far conflicts with a dependency
                dependent_requirement = required_by[requirement]
                raise VersionConflict(dist, requirement).with_context(
                    dependent_requirement
                )

            with lock:
                # push the new requirements onto the stack
                new_requirements = [
                    requirement
                    for requirement in dist.requires(requirement.extras)[::-1]
                    if requirement.key not in self.excludes
                ]
                req_stack.extend(new_requirements)

                # Register the new requirements needed by requirement
                for new_requirement in new_requirements:
                    required_by[new_requirement].add(requirement.project_name)
                    requirement_extras[new_requirement] = requirement.extras

                processed[requirement] = True

        req_stack = [
            r
            for (i, r) in enumerate(req_stack)
            if r not in req_stack[0:i]
            and r not in processed
            and requirement_extras.markers_pass(r, extras)
        ]
        with ThreadPoolExecutor() as executor:
            while req_stack:
                # process dependencies breadth-first
                reqs = req_stack[:]
                del req_stack[:]
                for _ in executor.map(resolve_requirement, reqs):
                    pass
                req_stack = [
                    r
                    for (i, r) in enumerate(req_stack)
                    if r not in req_stack[0:i]
                    and r not in processed
                    and requirement_extras.markers_pass(r, extras)
                ]

        # return list of distros to activate
        return resolved


class DistInstaller:
    def __init__(self, dist_dir: str, no_cache_dir: bool = False) -> None:
        self.dist_dir = path.realpath(dist_dir)
        self.no_cache_dir = no_cache_dir

    def fetch_dist(self, requirement):
        """Fetch an egg needed for building.
        Use pip/wheel to fetch/build a wheel."""
        get_distribution("pip")
        get_distribution("wheel")
        # Ignore environment markers; if supplied, it is required.
        requirement = Requirement.parse(str(requirement))
        requirement.marker = None
        # Take easy_install options into account, but do not override relevant
        # pip environment variables (like PIP_INDEX_URL or PIP_QUIET); they'll
        # take precedence.
        if "PIP_QUIET" in environ or "PIP_VERBOSE" in environ:
            quiet = False
        else:
            quiet = True
        index_url = None
        find_links = []
        environment = Environment()
        for dist in find_distributions(self.dist_dir):
            if dist in requirement and environment.can_add(dist):
                return dist
        with TemporaryDirectory() as tmpdir:
            cmd = [
                executable,
                "-m",
                "pip",
                "--disable-pip-version-check",
                "wheel",
                "--no-deps",
                "-w",
                tmpdir,
            ]
            if quiet:
                cmd.append("--quiet")
            if "PIP_NO_CACHE_DIR" not in environ and self.no_cache_dir:
                cmd.append("--no-cache-dir")
            if index_url is not None:
                cmd.extend(("--index-url", index_url))
            if find_links is not None:
                for link in find_links:
                    cmd.extend(("--find-links", link))
            # If requirement is a PEP 508 direct URL, directly pass
            # the URL to pip, as `req @ url` does not work on the
            # command line.
            if requirement.url:
                cmd.append(requirement.url)
            else:
                cmd.append(str(requirement))
            check_call(cmd)
            with ZipFile(glob(path.join(tmpdir, "*.whl"))[0], "r") as zf:
                zf.extractall(self.dist_dir)

            pattern = re_compile(
                translate(f'{requirement.project_name.replace("-","_")}-*.dist-info'),
                IGNORECASE,
            )
            dist_path = [
                path.join(self.dist_dir, x)
                for x in listdir(self.dist_dir)
                if path.isdir(path.join(self.dist_dir, x)) and match(pattern, x)
            ][0]

            root = path.dirname(dist_path)
            return Distribution.from_location(
                root,
                path.basename(dist_path),
                PathMetadata(root, dist_path),
                precedence=BINARY_DIST,
            )
