"""
Test cancelling an in-flight remote transfer (GitHub issue #131).

A remote copy is a single call into S3 or SFTP, so the byte-progress callback is
the only thread of control that comes back often enough to notice a cancel.
Raising from it has to unwind the transfer and reach the caller unchanged,
rather than being relabelled as a copy failure. The SFTP side of this is in
``test_ssh_sftp_session.py`` (``test_a_cancel_reaches_the_caller_unchanged``).

Run with: python -m pytest test/test_transfer_cancel.py -v
"""

import tempfile
import unittest
from unittest.mock import Mock, patch

from xefm.path import Path, copy_to
from xefm.s3 import clear_s3_cache
from xefm.task import Cancelled, Task


class TestS3TransferCancel(unittest.TestCase):
    """Cancelling a local <-> S3 copy from the progress callback"""

    def setUp(self):
        clear_s3_cache()
        self.temp_dir = tempfile.mkdtemp()
        self.content = b"x" * 4096
        self.local_file = Path(self.temp_dir) / "payload.bin"
        self.local_file.write_bytes(self.content)

        self.client = Mock()
        self.client.list_objects_v2.return_value = {'KeyCount': 0}
        self.client.head_object.return_value = {'ContentLength': len(self.content)}

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        clear_s3_cache()

    @patch('xefm.s3.boto3')
    def test_download_cancel_reaches_caller_unchanged(self, mock_boto3):
        """Cancelled from the callback is not folded into OSError"""
        mock_boto3.client.return_value = self.client

        def fake_download(Bucket, Key, Fileobj, Callback=None, **kwargs):
            for offset in range(0, len(self.content), 1024):
                Fileobj.write(self.content[offset:offset + 1024])
                Callback(1024)

        self.client.download_fileobj.side_effect = fake_download

        def cancel_after_one_chunk(copied, total):
            if copied > 0:
                raise Cancelled()

        dest = Path(self.temp_dir) / "downloaded.bin"
        with self.assertRaises(Cancelled):
            copy_to(Path("s3://bucket/payload.bin"), 
                dest, overwrite=True, progress_callback=cancel_after_one_chunk)

    @patch('xefm.s3.boto3')
    def test_cancelled_download_leaves_no_partial_file(self, mock_boto3):
        """A cancelled download does not leave a stub on disk"""
        mock_boto3.client.return_value = self.client

        def fake_download(Bucket, Key, Fileobj, Callback=None, **kwargs):
            Fileobj.write(self.content[:1024])
            Callback(1024)
            Fileobj.write(self.content[1024:])

        self.client.download_fileobj.side_effect = fake_download

        def cancel_after_one_chunk(copied, total):
            if copied > 0:
                raise Cancelled()

        dest = Path(self.temp_dir) / "downloaded.bin"
        with self.assertRaises(Cancelled):
            copy_to(Path("s3://bucket/payload.bin"), 
                dest, overwrite=True, progress_callback=cancel_after_one_chunk)

        self.assertFalse(dest.exists(),
                         "cancelled download should not be left on disk")

    @patch('xefm.s3.boto3')
    def test_upload_cancel_reaches_caller_unchanged(self, mock_boto3):
        """Same for the upload direction"""
        mock_boto3.client.return_value = self.client

        def fake_upload(Fileobj, Bucket, Key, Callback=None, **kwargs):
            Fileobj.read()
            Callback(1024)
            Callback(1024)

        self.client.upload_fileobj.side_effect = fake_upload

        def cancel_after_one_chunk(copied, total):
            if copied > 0:
                raise Cancelled()

        with self.assertRaises(Cancelled):
            copy_to(self.local_file, Path("s3://bucket/payload.bin"), overwrite=True,
                                    progress_callback=cancel_after_one_chunk)

    @patch('xefm.s3.boto3')
    def test_genuine_failure_is_still_an_oserror(self, mock_boto3):
        """Guarding the callback must not stop real errors becoming OSError"""
        mock_boto3.client.return_value = self.client
        self.client.upload_fileobj.side_effect = ValueError("bad bucket")

        with self.assertRaises(OSError):
            copy_to(self.local_file, Path("s3://bucket/payload.bin"), overwrite=True,
                                    progress_callback=lambda copied, total: None)


class TestRemoteProgressCheckpoint(unittest.TestCase):
    """file_operations wires cancellation into the byte-progress callback"""

    def test_forwards_progress_until_cancelled(self):
        from xefm.file_operations import FileOperationService

        task = Task("copy")
        prog = Mock()
        report = FileOperationService._remote_progress(task, prog, 3)

        report(512, 2048)
        prog.file_bytes.assert_called_once_with(3, 512, 2048)

        task.request_cancel()
        with self.assertRaises(Cancelled):
            report(1024, 2048)


if __name__ == '__main__':
    unittest.main()
