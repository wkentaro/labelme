import boto3
import json
import os
import threading
from labelme.logger import logger

class ProgressPercentage(object):
    def __init__(self, filename):
        self._filename = filename
        self._size = float(os.path.getsize(filename))
        self._seen_so_far = 0
        self._lock = threading.Lock()

    def __call__(self, bytes_amount):
        with self._lock:
            self._seen_so_far += bytes_amount
            percentage = (self._seen_so_far / self._size) * 100
            logger.info(
                "\r%s  %s / %s  (%.2f%%)" %
                (self._filename, self._seen_so_far, self._size, percentage)
            )

class aws_utils():
    input_bucket: str = ""
    output_bucket: str = ""
    aws_key_id: str = ""
    aws_secret_key: str = ""

    def __init__(self, aws_key_id="", aws_secret_key="", input_bucket="", output_bucket=""):
        self.input_bucket = input_bucket
        self.output_bucket = output_bucket
        self.aws_key_id = aws_key_id
        self.aws_secret_key = aws_secret_key

    def configure_login(self, aws_key_id, aws_secret_key):
        self.aws_key_id = aws_key_id
        self.aws_secret_key = aws_secret_key

    def configure_buckets(self, input_bucket, output_bucket):
        self.input_bucket = input_bucket
        self.output_bucket = output_bucket

    def read_from_s3(
        self,
        aws_fp,
        output_name,
        input_bucket = None,
        output_bucket = None
    ):

        if (input_bucket is None):
            input_bucket = self.input_bucket
        if (output_bucket is None):
            output_bucket = self.output_bucket

        s3 = boto3.client(
            's3',
            aws_access_key_id = self.aws_key_id,
            aws_secret_access_key = self.aws_secret_key
        )
        try:
            s3.download_file(
                input_bucket,
                aws_fp,
                output_name
            )
        except:
            logger.info("s3 download error for key {} to file {}".format(aws_fp, output_name))

    def output_s3(
        self,
        file_path,
        aws_fp,
        input_bucket = None,
        output_bucket = None
    ):

        if (input_bucket is None):
            input_bucket = self.input_bucket
        if (output_bucket is None):
            output_bucket = self.output_bucket

        config = boto3.s3.transfer.TransferConfig(
            multipart_threshold = 1024*25,
            max_concurrency = 10,
            multipart_chunksize = 1024*25,
            use_threads = True
        )

        s3_client = boto3.client(
            's3',
            aws_access_key_id = self.aws_key_id,
            aws_secret_access_key = self.aws_secret_key
        )

        s3_client.upload_file(
            file_path,
            output_bucket,
            aws_fp,
            Config = config,
            Callback = ProgressPercentage(file_path)
        )
