import os
import logging
import requests
from tqdm import tqdm

from OpenreviewScrape import openreview_utils
from OpenreviewScrape.definitions import PROJECT_ROOT_DIR


def download_spotlight_videos_pipeline(
    venues,
    conferences_name,
    cache_folder,
    limit_names_and_urls=None,
    credentials_file=None,
):
    from OpenreviewScrape.run_pipeline import scrape_conference

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
                logging.info(f"{note.content['spotlight']}")
                extension = note.content["spotlight"]["value"].split(".")[-1]
                title = openreview_utils.normalize_title(note.content["title"]["value"])
                logging.info(
                    f"Downloading spotlight video no. {i}\n\t{note.id}\n\t{title}"
                )
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

    logging.info(f"✓ Downloaded: {output_path}")
