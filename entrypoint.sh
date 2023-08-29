#!/bin/bash
# vfeeg-filestor file handling for eegFaktura
# Copyright (C) 2023  Matthias Poettinger
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#+

PYTHON=`which python3`


# TODEL if not required
#  OLD PSQL Check to verify if DB is read for connection -> moved to DOCKER healthcheck and conditional require
#PSQL=`which psql`
#
#check_pg_status() {
#  PGPASSWORD=$DB_PASSWORD $PSQL --host=$DB_HOSTNAME --username=$DB_USERNAME $DB_DATABASE -c "\conninfo" &>/dev/null
#  return $?
#}
#
## Wait for PSQL Server to be ready
#i=0
#
#until check_pg_status
#do
#  echo "Waiting for PostgreSQL Database to be ready ..."
#  sleep 5
#
#  if [ $i -eq 59 ]; then
#    echo "PostgreSQL did not start within 5 minutes"
#    echo "Stopping ..."
#    exit 1
#  fi
#
#  i=$((i+1))
#done

# Space for extra tasks
# Initialize DB
alembic upgrade head
# Run main.py
$PYTHON main.py
