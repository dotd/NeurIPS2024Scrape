import hashlib
import logging
import requests
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse
import time
from tqdm import tqdm


class PDFDownloader:
    """
    A utility class for downloading PDFs from URLs to a specified folder.
    """

    def __init__(
        self,
        download_folder: str,
        timeout: int = 30,
        retry_attempts: int = 3,
        delay_between_downloads: float = 0.5,
    ):
        """
        Initialize the PDF downloader.

        Args:
            download_folder: Path to the folder where PDFs will be downloaded
            timeout: Request timeout in seconds
            retry_attempts: Number of retry attempts for failed downloads
        """
        self.download_folder = Path(download_folder)
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.delay_between_downloads = delay_between_downloads
        # Create download folder if it doesn't exist
        self.download_folder.mkdir(parents=True, exist_ok=True)

    def download_pdf(
        self, url: str, filename: Optional[str] = None, additional_info=""
    ):
        """
        Download a single PDF from a URL.

        Args:
            url: URL of the PDF to download
            filename: Optional custom filename (if None, extracts from URL)

        Returns:
            Path to downloaded file if successful, None otherwise
        """
        if filename is None:
            filename = self._extract_filename_from_url(url)

        file_path = self.download_folder / filename

        # Skip if file already exists
        if file_path.exists():
            logging.info(f"{additional_info} File already exists: {file_path}")
            return str(file_path)

        for attempt in range(self.retry_attempts):
            try:
                logging.info(f"Downloading: {url}")
                response = requests.get(url, timeout=self.timeout, stream=True)
                response.raise_for_status()

                # Check if content is actually a PDF
                content_type = response.headers.get("content-type", "").lower()
                if "pdf" not in content_type and not url.lower().endswith(".pdf"):
                    logging.warning(
                        f"Warning: Content type is {content_type}, may not be a PDF"
                    )

                # Download with progress bar
                total_size = int(response.headers.get("content-length", 0))

                with open(file_path, "wb") as f:
                    with tqdm(
                        total=total_size, unit="B", unit_scale=True, desc=filename
                    ) as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))

                logging.info(f"{additional_info} Successfully downloaded: {file_path}")
                # Small delay between downloads to be respectful
                time.sleep(self.delay_between_downloads)
                return str(file_path)

            except requests.exceptions.RequestException as e:
                logging.error(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt < self.retry_attempts - 1:
                    time.sleep(2**attempt)  # Exponential backoff
                else:
                    logging.error(
                        f"Failed to download {url} after {self.retry_attempts} attempts"
                    )
                    return None

    def download_pdfs(
        self,
        pdf_urls: List[str],
        filenames: Optional[List[str]] = None,
        additional_info="",
    ):
        """
        Download multiple PDFs from a list of URLs.

        Args:
            pdf_urls: List of PDF URLs to download
            filenames: Optional list of custom filenames (must match length of pdf_urls)

        Returns:
            List of successfully downloaded file paths
        """
        if filenames and len(filenames) != len(pdf_urls):
            raise ValueError("Number of filenames must match number of URLs")

        downloaded_files = []

        logging.info(
            f"Starting download of {len(pdf_urls)} PDFs to {self.download_folder}"
        )

        for i, url in enumerate(pdf_urls):
            filename = filenames[i] if filenames else None
            file_path = self.download_pdf(url, filename, additional_info)

            if file_path:
                downloaded_files.append(file_path)

            logging.info(
                f"{additional_info} {i+1}/{len(pdf_urls)}: Downloaded {len(downloaded_files)} out of {len(pdf_urls)} PDFs"
            )
        return downloaded_files

    def _extract_filename_from_url(self, url: str) -> str:
        """
        Extract filename from URL, with fallback to URL hash.

        Args:
            url: URL to extract filename from

        Returns:
            Extracted filename with .pdf extension
        """
        parsed_url = urlparse(url)
        path = parsed_url.path

        # Try to get filename from path
        if path and "/" in path:
            filename = path.split("/")[-1]
            if filename and "." in filename:
                return filename

        # Fallback: use URL hash as filename
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        return f"pdf_{url_hash}.pdf"


def download_pdfs_simple(pdf_urls: List[str], folder: str) -> List[str]:
    """
    Simple function to download PDFs from a list of URLs to a folder.

    Args:
        pdf_urls: List of PDF URLs to download
        folder: Path to the folder where PDFs will be downloaded

    Returns:
        List of successfully downloaded file paths
    """
    downloader = PDFDownloader(folder)
    return downloader.download_pdfs(pdf_urls)
