import os
import logging
from OpenreviewScrape import openreview_utils
from OpenreviewScrape.definitions import PROJECT_ROOT_DIR
from OpenreviewScrape.pdf_downloader import PDFDownloader
import multiprocessing as mp
import requests
from tqdm import tqdm


venues = [
    # "ICML.cc/2025/Conference",
    # "ICLR.cc/2025/Conference",
    # "NeurIPS.cc/2024/Conference",
    # "ICML.cc/2024/Conference",
    # "ICLR.cc/2024/Conference",
    # "NeurIPS.cc/2023/Conference",
    # "robot-learning.org/CoRL/2024/Conference",
    # "robot-learning.org/CoRL/2025/Conference",
    "NeurIPS.cc/2025/Conference",
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
    "spotlight",
    "abstract",
]

conferences_name = "ConferencesData"


def download_spotlight_videos_pipeline(
    notes, cache_folder, limit_names_and_urls=None, credentials_file=None
):
    for venue_id in venues:
        safe_venue_id = openreview_utils.normalize_venue_id(venue_id)
        video_folder = (
            f"{PROJECT_ROOT_DIR}/{conferences_name}/{safe_venue_id}_spotlight_videos/"
        )
        # if folder does not exist, create it
        if not os.path.exists(video_folder):
            os.makedirs(video_folder)
        logging.info(f"Downloading PDFs {venue_id}")
        notes, _ = scrape_conference(venue_id, credentials_file, cache_folder)

        for i, note in enumerate(notes):
            if limit_names_and_urls is not None and i >= limit_names_and_urls:
                break
            if "spotlight" in note.content.keys():
                print(f"{note.content['spotlight']}")
                extension = note.content["spotlight"]["value"].split(".")[-1]
                title = openreview_utils.normalize_title(note.content["title"]["value"])
                print(f"Downloading spotlight video no. {i}\n\t{note.id}\n\t{title}")
                # path = f"{video_folder}" + f"/{note.id}_{i}_{title}.mp4"
                path = f"{video_folder}" + f"/{note.id}.{extension}"
                if os.path.exists(path):
                    continue
                download_openreview_video(
                    note.id,
                    # f"spotlight_{note.id}_{i}_{title}.{extension}",
                    f"{note.id}.{extension}",
                    output_path=path,
                )
        create_script_for_concatenation(
            video_folder, limit_names_and_urls=limit_names_and_urls
        )


def create_script_for_concatenation(video_folder, limit_names_and_urls=10000000):
    """
    ffmpeg -i 0ViTEgiFiQ.mp4 -i Bw9NHYjDqR.mp4 \
    -filter_complex "\
  [0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v0]; \
  [1:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v1]; \
  [v0][0:a][v1][1:a]concat=n=2:v=1:a=1[outv][outa]" \
  -map "[outv]" -map "[outa]" -c:v libx264 -c:a aac output.mp4
    """
    s = list()
    s.append(f"ffmpeg ")
    # get all videos in video_folder
    videos = [f for f in os.listdir(video_folder) if f.endswith(".mp4")]
    for video in videos[:limit_names_and_urls]:
        s.append(f"-i {video} ")
    s.append(f"\\\n")
    s.append(f'-filter_complex "\\\n')
    for i, video in enumerate(videos[:limit_names_and_urls]):
        s.append(
            f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}]; \\\n"
        )
    for i, video in enumerate(videos[:limit_names_and_urls]):
        s.append(f"[v{i}][{i}:a]")

    s.append(f'concat=n={len(videos[:limit_names_and_urls])}:v=1:a=1[outv][outa]" \\')
    s.append(
        f'-map "[outv]" -map "[outa]" -c:v libx264 -c:a aac {video_folder}/output.mp4 \n'
    )
    # save s into a file
    with open(f"{video_folder}/command.sh", "w") as f:
        f.write("".join(s))


def download_pdfs_pipeline(
    notes, cache_folder, limit_names_and_urls=None, credentials_file=None
):
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


def scrape_conferences_pipeline(
    limit_names_and_urls=10, download_pdfs=False, download_spotlight_videos=True
):
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

    if download_pdfs:
        download_pdfs_pipeline(
            notes,
            cache_folder,
            limit_names_and_urls=limit_names_and_urls,
            credentials_file=credentials_file,
        )

    if download_spotlight_videos:
        download_spotlight_videos_pipeline(
            notes,
            cache_folder,
            limit_names_and_urls=limit_names_and_urls,
            credentials_file=credentials_file,
        )


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


def download_openreview_video(paper_id, filename, output_path=None):
    """
    Download a video from OpenReview

    Args:
        paper_id: OpenReview paper ID
        filename: Name of the attachment
        output_path: Optional custom output filename
    """
    url = f"https://openreview.net/attachment?id={paper_id}&name=spotlight"

    if output_path is None:
        output_path = filename

    # Get file size for progress bar
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get("content-length", 0))

    # Download with progress bar
    with open(output_path, "wb") as f, tqdm(
        desc=output_path,
        total=total_size,
        unit="B",
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for chunk in response.iter_content(chunk_size=8192):
            size = f.write(chunk)
            bar.update(size)

    print(f"✓ Downloaded: {output_path}")


def scrape_conference(venue_id, credentials_file, cache_folder):
    table = list()
    values_venue = set()
    counter = 0
    notes_filtered = list()

    notes = openreview_utils.get_conference(
        credentials_file=credentials_file, venue_id=venue_id, cache_folder=cache_folder
    )
    # Open link to google drive and make a new sheet

    # get first note and print its content fields
    logging.info("\n" + str(notes[0].content.keys()))
    for i, note in enumerate(notes):
        if "Bw9NHYjDqR" in note.id:
            print(note.content)
        values_venue.add(note.content["venue"]["value"])
        print(f"venue: {note.content['venue']['value']} {i}")
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
                if (
                    field == "pdf"
                    or field == "supplementary_material"
                    or field == "spotlight"
                ):
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


def tst_download_video(
    id="Bw9NHYjDqR",
):
    download_openreview_video(id, "spotlight_video.mp4")


if __name__ == "__main__":
    # tst_download_video()
    scrape_conferences_pipeline(download_pdfs=True)
