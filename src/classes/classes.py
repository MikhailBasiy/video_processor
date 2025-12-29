import re
from functools import cache
import subprocess

import pandas as pd
import yt_dlp

from utils.logger import get_logger
from s3_client import get_s3_client

logger = get_logger(__name__)


class VideoProcessor:
    def __init__(self):
        self.data = pd.read_excel("data/data.xlsx")
        self.re_pattern = 'src=".*?"'
        self.ydl_opts = {
            "outtmpl": "%(title)s.%(ext)s",
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
        }

    def launch(self):
        for value in self.data.values:
            urls: list[str] = self._get_urls(value[3])
            for url in urls:
                logger.info(url)
                new_url = self._process_video(url)

    def _get_urls(self, html_tag: str) -> list[str]:
        return re.findall(self.re_pattern, html_tag)

    @cache
    def _process_video(self, url: str) -> str:
        pass
