import os
import logging
from OpenreviewScrape import openreview_utils
from OpenreviewScrape.definitions import PROJECT_ROOT_DIR
from OpenreviewScrape.pdf_downloader import PDFDownloader
import multiprocessing as mp


venues = [
    # "ICML.cc/2025/Conference",
    # "ICLR.cc/2025/Conference",
    # "NeurIPS.cc/2024/Conference",
    # "ICML.cc/2024/Conference",
    # "ICLR.cc/2024/Conference",
    # "NeurIPS.cc/2023/Conference",
    # "robot-learning.org/CoRL/2024/Conference",
    "robot-learning.org/CoRL/2025/Conference",
]

fields = [
    "title",
    "authors",
    "keywords",
    "primary_area",
    "venue",
    "pdf",
    "supplementary_material",
    "TLDR",
    "abstract",
]

conferences_name = "ConferencesData"


def scrape_conferences(limit_names_and_urls=None):
    openreview_utils.prepare_parameters_and_logging()
    credentials_file = f"{PROJECT_ROOT_DIR}/credentials/openreview_api.txt"
    cache_folder = f"{PROJECT_ROOT_DIR}/{conferences_name}/"

    for venue_id in venues:
        safe_venue_id = openreview_utils.normalize_venue_id(venue_id)
        logging.info(f"Scraping {venue_id}")
        notes, table = scrape_conference(venue_id, credentials_file, cache_folder)

        # save table to file
        safe_venue_id = openreview_utils.normalize_venue_id(venue_id)
        with open(
            f"{PROJECT_ROOT_DIR}/{conferences_name}/{safe_venue_id}.csv", "w"
        ) as f:
            f.write(table)

    processes = []
    for venue_id in venues:
        safe_venue_id = openreview_utils.normalize_venue_id(venue_id)
        pdf_folder = f"{PROJECT_ROOT_DIR}/{conferences_name}/{safe_venue_id}/"
        logging.info(f"Downloading PDFs {venue_id}")
        notes, table = scrape_conference(venue_id, credentials_file, cache_folder)

        names_and_urls = openreview_utils.get_pdfs_names_and_urls(notes)
        if limit_names_and_urls is not None:
            names_and_urls = names_and_urls[:limit_names_and_urls]
        urls = [url for _, url in names_and_urls]
        titles = [title for title, _ in names_and_urls]

        # Create and start a new process for each venue
        p = mp.Process(target=download_pdfs, args=(urls, pdf_folder, titles, venue_id))
        p.start()
        processes.append(p)

    # Wait for all processes to complete
    for p in processes:
        p.join()


def download_pdfs(pdf_urls, cache_folder, titles=None, additional_info=""):

    # Advanced usage with custom settings
    downloader = PDFDownloader(
        download_folder=cache_folder,
        timeout=60,
        retry_attempts=5,
        delay_between_downloads=0.25,
    )
    downloaded_files = downloader.download_pdfs(
        pdf_urls, titles, additional_info=additional_info
    )


def scrape_conference(venue_id, credentials_file, cache_folder):
    notes = openreview_utils.get_conference(
        credentials_file=credentials_file, venue_id=venue_id, cache_folder=cache_folder
    )
    # Open link to google drive and make a new sheet

    table = list()
    values_venue = set()
    counter = 0
    notes_filtered = list()
    # get first note and print its content fields
    logging.info("\n" + str(notes[0].content.keys()))
    for note in notes:
        values_venue.add(note.content["venue"]["value"])
        line = list()
        if (
            "poster" not in note.content["venue"]["value"].lower()
            and "spotlight" not in note.content["venue"]["value"].lower()
            and "talk" not in note.content["venue"]["value"].lower()
            and "oral" not in note.content["venue"]["value"].lower()
            and "corl 2024" not in note.content["venue"]["value"].lower()
        ):
            continue
        notes_filtered.append(note)
        counter += 1
        for field in fields:
            if field in note.content:
                value = (
                    note.content[field]["value"]
                    if type(note.content[field]["value"]) == str
                    else ";".join(note.content[field]["value"])
                )
                if field == "pdf" or field == "supplementary_material":
                    value = f"https://openreview.net{value}"
                value = value.replace("\t", "").replace("\n", "")
                line.append(value)
            else:
                line.append("")
        table.append("\t".join(line))
    logging.info(f"Scraped valid papers: {counter}")
    logging.info("\n".join(list(values_venue)))
    table = "\n".join(table)
    # if {conferences_name} folder does not exist, create it
    if not os.path.exists(f"{PROJECT_ROOT_DIR}/{conferences_name}"):
        os.makedirs(f"{PROJECT_ROOT_DIR}/{conferences_name}")

    return notes_filtered, table


if __name__ == "__main__":
    scrape_conferences()
