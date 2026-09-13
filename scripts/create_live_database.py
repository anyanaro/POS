"""Create the empty deployable PostgreSQL database used by the live site."""

import os
import sys

import psycopg2
from psycopg2 import sql


def main():
    database_name = sys.argv[1] if len(sys.argv) > 1 else "POS Live"
    connection = psycopg2.connect(
        dbname=os.environ.get("DB_ADMIN_NAME", "postgres"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ["DB_PASSWORD"],
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
    )
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", [database_name])
        if cursor.fetchone():
            print(f"Database already exists: {database_name}")
            return
        cursor.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8'").format(sql.Identifier(database_name)))
    connection.close()
    print(f"Created empty database: {database_name}")


if __name__ == "__main__":
    main()