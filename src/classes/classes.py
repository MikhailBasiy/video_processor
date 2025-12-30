import re
import subprocess
import threading
import pandas as pd
import yt_dlp
from settings import BUCKET, DATA_DIR, DOMAIN, EXTENSION, SERIES_MAP
from dotenv import load_dotenv

from utils.logger import get_logger
from s3_client import client

logger = get_logger(__name__)

load_dotenv()


class VideoProcessor:
    def __init__(self):
        self.data = pd.read_excel("data/data.xlsx")
        self.re_pattern = r'src="([^"]+)"'

        self.s3_client = client
        self.domain = DOMAIN
        self.bucket = BUCKET
        self.extension = EXTENSION
        self.ydl_opts = {
            "outtmpl": "%(title)s.%(ext)s",
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": {self.extension},
        }
        self.chunk_size = 5 * 1024 * 1024
        self.cache = {}

    def launch(self):
        results: list[list[str]] = []
        data: list[list[str]] = self.data.values.tolist()
        for video_data in data:
            urls: list[str] = self._get_urls(video_data[3])
            for url in urls:
                if url in self.cache:
                    logger.info(f"Данное видео уже обработано. Возвращаю ссылку из кеша. {url}")
                    video_data.append(self.cache[url])
                else:
                    logger.info(f"Обрабатываю видео по ссылке: {url}")
                    key: str = self._get_key(video_data[1])
                    if self._process_video(url, key):
                        video_data.append(key)
                        logger.info(f"Видео {url} успешно загружено в хранилище с ключом {key}")
                        self.cache[url] = key
            results.append(video_data)
        pd.DataFrame(results).to_excel(f"{DATA_DIR}/result.xlsx", engine="xlsxwriter", index=False)

    def _get_urls(self, html_tag: str) -> list[str]:
        return re.findall(self.re_pattern, html_tag)

    def _get_key(self, series: str) -> str:
        series = SERIES_MAP.get(series)
        video_num = 1
        key = f"{series + '/' if series else None}{str(video_num)}.{self.extension}"
        while True:
            if key in self.cache.values():
                logger.info(f"Ключ уже занят: {key}")
                video_num += 1
                key = f"{series}/{str(video_num)}.{self.extension}"
            else:
                logger.info(f"Уникальный ключ: {key}")
                return key

    def _process_video(self, url: str, key: str) -> bool:
        ydlp = subprocess.Popen(
            [
                "yt-dlp",
                "-f", "bestvideo+bestaudio/best",
                "-o", "-",  # вывод в stdout
                url,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        ffmpeg = subprocess.Popen(
            [
                "ffmpeg",
                "-i", "pipe:0",
                "-c", "copy",
                "-bsf:a", "aac_adtstoasc",
                "-movflags", "frag_keyframe+empty_moov",
                "-f", self.extension,
                "pipe:1",
            ],
            stdin=ydlp.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        if ydlp.stdout:
            ydlp.stdout.close()

        multipart = self.s3_client.create_multipart_upload(
            Bucket=self.bucket,
            Key=key,
            ContentType=f"video/{self.extension}",
        )
        upload_id = multipart["UploadId"]
        parts = []
        part_number = 1
        stop_threads = False

        # Буфер для чтения ffmpeg stdout
        ffmpeg_chunks = []

        # Thread для чтения stdout ffmpeg
        def read_stdout():
            nonlocal ffmpeg_chunks, stop_threads
            while not stop_threads:
                chunk = ffmpeg.stdout.read(self.chunk_size)
                if not chunk:
                    break
                ffmpeg_chunks.append(chunk)

        # Thread для чтения stderr ffmpeg/yt-dlp и логирования
        def read_stderr(proc, name):
            while not stop_threads:
                line = proc.stderr.readline()
                if not line:
                    break
                logger.error(f"{name}: {line.decode(errors='ignore').strip()}")

        t_stdout = threading.Thread(target=read_stdout)
        t_ffmpeg_stderr = threading.Thread(target=read_stderr, args=(ffmpeg, "ffmpeg"))
        t_ydlp_stderr = threading.Thread(target=read_stderr, args=(ydlp, "yt-dlp"))

        t_stdout.start()
        t_ffmpeg_stderr.start()
        t_ydlp_stderr.start()

        try:
            t_stdout.join()
            t_ffmpeg_stderr.join()
            t_ydlp_stderr.join()

            ffmpeg.wait()
            ydlp.wait()

            if ffmpeg.returncode != 0:
                raise RuntimeError("ffmpeg завершился с ошибкой")
            if ydlp.returncode != 0:
                raise RuntimeError("yt-dlp завершился с ошибкой")

            # Загружаем в S3
            for chunk in ffmpeg_chunks:
                response = self.s3_client.upload_part(
                    Bucket=self.bucket,
                    Key=key,
                    UploadId=upload_id,
                    PartNumber=part_number,
                    Body=chunk,
                )
                parts.append({"PartNumber": part_number, "ETag": response["ETag"]})
                part_number += 1

            self.s3_client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )

            return True

        except Exception:
            self.s3_client.abort_multipart_upload(
                Bucket=self.bucket,
                Key=key,
                UploadId=upload_id,
            )
            raise

        finally:
            stop_threads = True
            if ffmpeg.stdout:
                ffmpeg.stdout.close()
            if ffmpeg.stderr:
                ffmpeg.stderr.close()
            if ydlp.stderr:
                ydlp.stderr.close()
