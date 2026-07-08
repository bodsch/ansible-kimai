#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Ansible filter plugin to build a Doctrine DBAL / Symfony compatible
``DATABASE_URL`` connection string from a structured database connection fact.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ansible.errors import AnsibleFilterError
from ansible.utils.display import Display

display = Display()

DOCUMENTATION = r"""
  name: database_string
  short_description: Build a Doctrine DBAL DATABASE_URL connection string

  description:
    - Build a MySQL/MariaDB compatible C(DATABASE_URL) connection string as
      consumed by Doctrine DBAL / Symfony applications (e.g. Kimai).
    - Appends C(serverVersion) when C(server.version) is present in the input
      data, typically produced by the C(add_database_version) filter.
    - Username and password are percent-encoded to keep the resulting URL
      valid even when they contain reserved characters such as C(@), C(:), or C(/).

  positional: _input

  options:
    _input:
      description:
        - Structured database connection data.
      type: dict
      required: true
      suboptions:
        username:
          description: Database username.
          type: str
          required: true
        password:
          description: Database password.
          type: str
          required: true
        hostname:
          description: Database hostname or IP address.
          type: str
          required: true
        port:
          description: Database port.
          type: int
          required: true
        schema:
          description: Database schema / name.
          type: str
          required: true
        charset:
          description: Connection charset.
          type: str
          default: utf8
        server:
          description: Optional server version information.
          type: dict
          suboptions:
            version:
              description:
                - Normalized server version, e.g. C(mariadb-10.6.14) or C(8.0.35).
              type: str

  author:
    - Bodo Schulz
"""

EXAMPLES = r"""
- name: Build the DATABASE_URL for Kimai
  ansible.builtin.set_fact:
    kimai_database_url: "{{ database_connection | database_string }}"
  vars:
    database_connection:
      username: kimai
      password: secret
      hostname: 127.0.0.1
      port: 3306
      schema: kimai
      charset: utf8
      server:
        version: mariadb-10.6.14
"""

RETURN = r"""
  _value:
    description:
      - The assembled C(DATABASE_URL) connection string.
    type: str
    sample: "mysql://kimai:secret@127.0.0.1:3306/kimai?utf8&serverVersion=mariadb-10.6.14"
"""

#: Data keys that must be present (and truthy) to build a valid connection string.
_REQUIRED_KEYS: tuple[str, ...] = ("username", "password", "hostname", "port", "schema")


class FilterModule(object):
    """
    Ansible jinja2 filter plugin providing the C(database_string) filter.
    """

    def filters(self) -> dict[str, Any]:
        """
        Register the filters provided by this plugin.

        Returns:
            A mapping of filter name to the callable implementing it.
        """
        return {
            "database_string": self.database_string,
        }

    def database_string(self, data: dict[str, Any]) -> str:
        """
        Build a Doctrine DBAL compatible ``DATABASE_URL`` connection string.

        For MySQL, this produces a string such as::

            mysql://user:password@127.0.0.1:3306/database?charset=utf8&serverVersion=5.7

        For MariaDB, ``serverVersion`` is prefixed accordingly::

            mysql://user:password@127.0.0.1:3306/database?charset=utf8&serverVersion=mariadb-10.5.8

        Args:
            data:
                Structured database connection data. Must contain ``username``,
                ``password``, ``hostname``, ``port``, and ``schema``. May
                optionally contain ``charset`` (default ``utf8``) and
                ``server.version``.

        Returns:
            The assembled ``DATABASE_URL`` connection string, with ``username``
            and ``password`` percent-encoded.

        Raises:
            AnsibleFilterError:
                If ``data`` is not a mapping, or any required key is missing
                or empty.
        """
        if not isinstance(data, dict):
            raise AnsibleFilterError(f"database_string() requires a mapping, got: {data!r}")

        missing = [key for key in _REQUIRED_KEYS if not data.get(key)]
        if missing:
            raise AnsibleFilterError(
                f"database_string() is missing required key(s): {', '.join(missing)}"
            )

        dba_username = quote(str(data["username"]), safe="")
        dba_password = quote(str(data["password"]), safe="")
        dba_hostname = data["hostname"]
        dba_port = data["port"]
        dba_schema = data["schema"]
        dba_charset = data.get("charset", "utf8")
        dba_server_version = data.get("server", {}).get("version")

        dba_string = (
            f"mysql://{dba_username}:{dba_password}@{dba_hostname}:{dba_port}"
            f"/{dba_schema}?{dba_charset}"
        )

        if dba_server_version:
            dba_string += f"&serverVersion={dba_server_version}"

        display.vv(f"= return : {dba_string}")

        return dba_string
