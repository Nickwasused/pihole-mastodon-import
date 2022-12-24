#!/bin/python3
from dotenv import load_dotenv
from pathlib import Path
from os import getenv, system
import numpy as np
import requests
import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logging.getLogger().setLevel(logging.INFO)
load_dotenv()

database_file = Path(__file__).parent.absolute().joinpath('domains.sqlite')
# create the database if it does not exist
connection = sqlite3.connect(database_file)
connection.execute("CREATE TABLE IF NOT EXISTS domains(id INTEGER PRIMARY KEY AUTOINCREMENT, domain VARCHAR(256));")
connection.commit()
connection.close()


def whitelist_urls(add_urls):
    logging.info(f"adding {len(add_urls)} to whitelist")
    w_connection = sqlite3.connect(database_file)
    w_cursor = w_connection.cursor()
    w_cursor.execute("BEGIN")
    for url in add_urls:
        w_cursor.execute("INSERT INTO domains (domain) VALUES (?);", (url,))
    w_cursor.execute("COMMIT;")
    w_connection.commit()
    w_connection.close()

    for urls in np.array_split(add_urls, 100):
        command = 'pihole -w -nr -q '
        for url in urls:
            command += f"{url} "

        command += '--comment "mastodon instance"'
        system(command)

    system("pihole restartdns")


def remove_urls_whitelist(remove_urls):
    logging.info(f"removing {len(remove_urls)} from whitelist")
    r_connection = sqlite3.connect(database_file)
    r_cursor = r_connection.cursor()
    r_cursor.execute("BEGIN")
    for url in remove_urls:
        r_cursor.execute("DELETE FROM domains WHERE domain=?;", (url,))
    r_cursor.execute("COMMIT;")
    r_connection.commit()
    r_connection.close()

    command = 'pihole -w -d '
    for url in remove_urls:
        command += f"{url} "

    system(command)


def get_database_urls():
    l_connection = sqlite3.connect(database_file)
    l_cursor = l_connection.cursor()
    l_cursor.execute("SELECT domain FROM domains;")
    rows = l_cursor.fetchall()
    urls = []
    for row in rows:
        urls.append(row[0])
    l_connection.close()

    return urls


def get_remote_urls():
    instance_urls = []
    fetching = True
    next_id = 0

    params = {
        "count": "1000",
        "include_dead": "false",
        "include_down": "false",
        "include_closed": "true",
        "min_users": "2",
        "min_version": "3.0.0"
    }

    while fetching:
        if next_id != 0:
            params['min_id'] = next_id

        instance_data = requests.get("https://instances.social/api/1.0/instances/list", params=params, headers={
            "Authorization": f"Bearer {getenv('API_TOKEN')}"
        }).json()

        for instance in instance_data["instances"]:
            instance_urls.append(instance["name"])

        try:
            next_id = instance_data["pagination"]["next_id"]
        except KeyError:
            logging.info("done with fetching instances")
            fetching = False

    instance_urls = list(set(instance_urls))
    logging.info(f"got {len(instance_urls)} instances")

    return instance_urls


def update_urls(local_urls, remote_urls):
    remove_urls = []
    add_urls = []

    for url in remote_urls:
        if url in local_urls:
            # do nothing
            pass
        elif url not in local_urls:
            # add url to whitelist
            add_urls.append(url)

    for url in local_urls:
        if url not in remote_urls:
            # a local domain is not in the whitelist lets remove it
            remove_urls.append(url)

    whitelist_urls(add_urls)
    remove_urls_whitelist(remove_urls)


if __name__ == "__main__":
    update_urls(get_database_urls(), get_remote_urls())
