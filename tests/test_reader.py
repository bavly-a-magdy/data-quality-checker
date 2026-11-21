import pytest
from dq_checker.reader import read_csv_bytes, DataReadError
def test_read_text_preserved():
    assert read_csv_bytes(b"n\n001\n").iloc[0,0]=="001"
def test_empty_file_message():
    with pytest.raises(DataReadError,match="empty"): read_csv_bytes(b"")
def test_wrong_delimiter():
    with pytest.raises(DataReadError,match="delimiter"): read_csv_bytes(b"a;b\n1;2\n")
