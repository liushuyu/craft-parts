# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2015-2021 Canonical Ltd.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Implement the tar source handler."""

import os
import re
import tarfile
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from overrides import overrides

from .base import (
    BaseFileSourceModel,
    FileSourceHandler,
    get_json_extra_schema,
    get_model_config,
)


class TarSourceModel(BaseFileSourceModel, frozen=True):  # type: ignore[misc]
    """Pydantic model for a tar file source."""

    model_config = get_model_config(
        get_json_extra_schema(r"\.(tar(\.[a-z0-9]+)?|tgz)$")
    )
    source_type: Literal["tar"] = "tar"


class TarSource(FileSourceHandler):
    """The tar source handler."""

    source_model = TarSourceModel

    @overrides
    def provision(
        self,
        dst: Path,
        keep: bool = False,  # noqa: FBT001, FBT002
        src: Path | None = None,
    ) -> None:
        """Extract tarball contents to the part source dir."""
        tarball = src if src else self.part_src_dir / os.path.basename(self.source)

        _extract(tarball, dst)

        if not keep:
            os.remove(tarball)


def _extract(tarball: Path, dst: Path) -> None:
    with tarfile.open(tarball) as tar:

        def filter_members(tar: tarfile.TarFile) -> Iterator[tarfile.TarInfo]:
            """Strip common prefix and ban dangerous names."""
            members = tar.getmembers()
            common = os.path.commonprefix([m.name for m in members])

            # commonprefix() works a character at a time and will
            # consider "d/ab" and "d/abc" to have common prefix "d/ab";
            # check all members either start with common dir
            for member in members:
                if not (
                    member.name.startswith(common + "/")
                    or member.isdir()
                    and member.name == common
                ):
                    # commonprefix() didn't return a dir name; go up one
                    # level
                    common = os.path.dirname(common)
                    break

            for member in members:
                if member.name == common:
                    continue
                _strip_prefix(common, member)
                # We mask all files to be writable to be able to easily
                # extract on top.
                member.mode = member.mode | 0o200
                yield member

        # ignore type, members expect List but we're providing Generator
        tar.extractall(members=filter_members(tar), path=dst)


def _strip_prefix(common: str, member: tarfile.TarInfo) -> None:
    if member.name.startswith(common + "/"):
        member.name = member.name[len(common + "/") :]
    # strip leading '/', './' or '../' as many times as needed
    member.name = re.sub(r"^(\.{0,2}/)*", r"", member.name)
    # do the same for linkname if this is a hardlink
    if member.islnk() and not member.issym():
        if member.linkname.startswith(common + "/"):
            member.linkname = member.linkname[len(common + "/") :]
        member.linkname = re.sub(r"^(\.{0,2}/)*", r"", member.linkname)
