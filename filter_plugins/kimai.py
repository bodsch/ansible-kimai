# python 3 headers, required if submitting to Ansible
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

from ansible.utils.display import Display

display = Display()


class FilterModule(object):
    """
        Ansible file jinja2 tests
    """

    def filters(self):
        return {
            'database_string': self.database_string,
            'add_database_version': self.add_database_version,
        }

    def database_string(self, data):
        """
           For MySQL that would be "serverVersion=5.7" as in:
              DATABASE_URL=mysql://user:password@127.0.0.1:3306/database?charset=utf8&serverVersion=5.7

           For MariaDB it would be "serverVersion=mariadb-10.5.8":
              DATABASE_URL=mysql://user:password@127.0.0.1:3306/database?charset=utf8&serverVersion=mariadb-10.5.8
        """
        dba_string = None

        dba_username = data.get("username")
        dba_password = data.get("password")
        dba_hostname = data.get("hostname")
        dba_port = data.get("port")
        dba_schema = data.get("schema")
        dba_charset = data.get("charset", "utf8")
        dba_server_version = data.get("server", {}).get("version")

        dba_string = f"mysql://{dba_username}:{dba_password}@{dba_hostname}:{dba_port}/{dba_schema}?{dba_charset}"

        if dba_server_version:
            dba_string += f"&serverVersion={dba_server_version}"

        display.v(f"= return : {dba_string}")

        return dba_string

    def add_database_version(self, data, dba_version):
        """
          version:
            full: 10.6.14-MariaDB-1:10.6.14+maria~deb11-log
            major: 10
            minor: 6
            release: 14
            suffix: MariaDB-1:10
        """
        display.v(f"add_database_version(self, {data}, {dba_version})")

        version_data = dba_version.get("version")


        is_mariadb = False
        _version = f"{version_data.get('major')}.{version_data.get('minor')}.{version_data.get('release')}"

        if "mariadb" in version_data.get("suffix").lower():
            is_mariadb = True

            data["server"]["version"] = f"mariadb-{_version}"
        else:
            data["server"]["version"] = f"{_version}"

        display.v(f"= return : {data}")

        return data
