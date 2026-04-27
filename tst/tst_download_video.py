from OpenreviewScrape.video_utils import download_openreview_video


def tst_download_video(
    id="Bw9NHYjDqR",
):
    download_openreview_video(id, "spotlight_video.mp4")


if __name__ == "__main__":
    tst_download_video()
