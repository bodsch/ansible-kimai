#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible filter plugin to derive a normalized database server version string
from a detected database version fact and write it into a connection data
structure, for use by Doctrine DBAL / Symfony's ``DATABASE_URL`` (e.g. via the
:mod:`database_string` filter).
"""

from __future__ import annotations

from typing import Any

from ansible.errors import AnsibleFilterError
from ansible.utils.display import Display

display = Display()

DOCUMENTATION = r"""
  name: add_database_version
  short_description: Add a normalized database server version to a data structure

  description:
    - Read C(major), C(minor), C(release), and C(suffix) from a detected
      database version fact and write a normalized C(server.version) string
      into the given data dictionary.
    - MariaDB versions are prefixed with C(mariadb-), matching the format
      expected by Doctrine DBAL / Symfony's C(DATABASE_URL) C(serverVersion).

  positional: _input, dba_version

  options:
    _input:
      description:
        - Data structure to update. Must already contain a C(server) mapping;
          the resulting version string is written to C(server.version).
      type: dict
      required: true
    dba_version:
      description:
        - Detected database version fact.
        - Must contain a C(version) mapping with the keys C(major), C(minor),
          C(release), and C(suffix).
      type: dict
      required: true

  author:
    - Bodo Schulz
"""

EXAMPLES = r"""
- name: Add the detected database version to the connection data
  ansible.builtin.set_fact:
    database_connection: "{{ database_connection | add_database_version(mariadb_version) }}"
  vars:
    mariadb_version:
      version:
        full: "10.6.14-MariaDB-1:10.6.14+maria~deb11-log"
        major: 10
        minor: 6
        release: 14
        suffix: "MariaDB-1:10"
"""

RETURN = r"""
  _value:
    description:
      - The input data structure with C(server.version) set to the normalized
        version string, e.g. C(mariadb-10.6.14) or C(8.0.35).
    type: dict
"""


class FilterModule(object):
    """
    Ansible jinja2 filter plugin providing the C(add_database_version) filter.
    """

    def filters(self) -> dict[str, Any]:
        """
        Register the filters provided by this plugin.

        Returns:
            A mapping of filter name to the callable implementing it.
        """
        return {
            "add_database_version": self.add_database_version,
        }

    def add_database_version(
        self, data: dict[str, Any], dba_version: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Write a normalized database server version string into ``data['server']['version']``.

        Args:
            data:
                Data structure to update. Must already contain a ``server`` mapping.
            dba_version:
                Detected database version fact, containing a ``version`` mapping
                with ``major``, ``minor``, ``release``, and ``suffix``.

        Returns:
            The updated ``data`` dictionary (mutated in place and returned).

        Raises:
            AnsibleFilterError:
                If ``dba_version`` does not contain a usable ``version`` mapping,
                required version components are missing, or ``data`` does not
                contain a ``server`` mapping.
        """
        display.vv(f"add_database_version(data: {data}, dba_version: {dba_version})")

        version_data = dba_version.get("version") if isinstance(dba_version, dict) else None

        if not isinstance(version_data, dict):
            raise AnsibleFilterError(
                "add_database_version() requires 'dba_version.version' to be a mapping "
                f"with 'major', 'minor', 'release' and 'suffix' keys, got: {dba_version!r}"
            )

        major = version_data.get("major")
        minor = version_data.get("minor")
        release = version_data.get("release")
        suffix = version_data.get("suffix") or ""

        if major is None or minor is None or release is None:
            raise AnsibleFilterError(
                "add_database_version() requires 'major', 'minor' and 'release' "
                f"to be set in 'dba_version.version', got: {version_data!r}"
            )

        if not isinstance(data, dict) or not isinstance(data.get("server"), dict):
            raise AnsibleFilterError(
                "add_database_version() requires the input data to contain a "
                f"'server' mapping, got: {data!r}"
            )

        version = f"{major}.{minor}.{release}"

        if "mariadb" in str(suffix).lower():
            data["server"]["version"] = f"mariadb-{version}"
        else:
            data["server"]["version"] = version

        return data
