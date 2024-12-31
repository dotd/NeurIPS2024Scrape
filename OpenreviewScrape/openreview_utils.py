import pickle
import logging
import argparse
import logging
import os
from pathlib import Path
import time

import openreview
from OpenreviewScrape.definitions import PROJECT_ROOT_DIR


def prepare_parameters_and_logging(log_level="INFO",
                                   log_folder="./logs/",
                                   arguments=None,
                                   skip_main_to_screen=True,
                                   ):
    """

    :param log_level:
    :param log_folder:
    :param arguments:

    :param skip_main_to_screen:
    :return:
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--signature", type=str, default=time.strftime("%Y%m%d_%H%M%S"))
    if arguments is not None:
        for arg in arguments:
            parser.add_argument(arg[0], type=arg[1], default=arg[2])
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default=log_level,
        help="Set the logging level (default is DEBUG).",
    )

    args = parser.parse_args()
    filename_full = os.path.abspath(__file__)
    filename = filename_full.split("/")[-1].split(".")[0]
    log_file = f"{log_folder}/{filename}_{args.signature}.log"
    log_file_latest = f"{log_folder}/{filename}.log"
    os.makedirs(f"{log_folder}") if not os.path.exists(f"{log_folder}") else None
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        handlers=[
            logging.FileHandler(log_file),
            logging.FileHandler(log_file_latest),
            logging.StreamHandler(),
        ],
        format="%(levelname)s: %(message)s",
    )

    # Put into logging the file itself for debugging
    logging.info(f"Running file: {filename_full}")
    logging.info(f"log_file: {log_file}, skip_main_to_screen={skip_main_to_screen}")
    if not skip_main_to_screen:
        logging.info(f"Log file:\n{'start_of_running_file'.upper()}\n")
        f"{Path(filename_full).read_text()}\n{'end_of_running_file'.upper()}"

    for arg, value in vars(args).items():
        logging.info(f"{__file__.split('/')[-1]}> {arg}: {value}")
    return args


def get_client(credentials_file):
    # get file from credential/openreview_api.txt
    with open(credentials_file) as f:
        lines = f.readlines()
        username = lines[0].strip()
        password = lines[1].strip()
    client = openreview.api.OpenReviewClient(
        baseurl='https://api2.openreview.net',
        username=username,
        password=password
    )
    return client


def show_all_venues(client):
    # API V2

    venues = client.get_group(id='venues').members
    for i, venue in enumerate(venues):
        if venue.startswith('NeurIPS'):
            print(f"{i} => {venue}")


def normalize_venue_id(venue_id):
    return venue_id.replace(" ", "_").replace("/", "_").replace(":", "_").replace(".", "_")


def get_notes_helper(client, venue_id):
    notes = client.get_all_notes(invitation=f"{venue_id}/-/Submission")
    return notes


def get_conference(
        credentials_file,
        venue_id,
        cache_folder
):
    # if cache folder does not exist, create it
    if not os.path.exists(cache_folder):
        os.makedirs(cache_folder)
    filename = normalize_venue_id(venue_id) + ".pkl"
    full_path = f"{cache_folder}/{filename}"
    if os.path.exists(full_path):
        logging.info(f"Loading from cache: {full_path}")
        with open(full_path, 'rb') as f:
            notes = pickle.load(f)
    else:
        logging.info(f"Downloading from Polygon API")
        client = get_client(credentials_file)
        notes = get_notes_helper(client, venue_id)
        with open(full_path, 'wb') as f:
            pickle.dump(notes, f)

    return notes
