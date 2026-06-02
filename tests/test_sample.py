from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import zipfile

from rdflib import Graph, URIRef

from rdf_dataset_stats import sample


EX = "http://example.org/"


@dataclass
class FakeRecord:
    graph: Graph
    subdataset: str
    record_path: str


class FakeRDFDumpReader:
    calls: list[tuple[object, str, str]] = []
    records: list[FakeRecord] = []

    def __init__(
        self, input_path: object, on_parse_error: str, invalid_uri_policy: str
    ) -> None:
        self.calls.append((input_path, on_parse_error, invalid_uri_policy))
        self._index = 0
        self._skip_subdataset: str | None = None

    def __iter__(self):
        return self

    def __next__(self) -> FakeRecord:
        while self._index < len(self.records):
            record = self.records[self._index]
            self._index += 1
            if record.subdataset == self._skip_subdataset:
                continue
            self._skip_subdataset = None
            return record
        raise StopIteration

    def skip_subdataset(self) -> None:
        if 0 < self._index <= len(self.records):
            self._skip_subdataset = self.records[self._index - 1].subdataset


def matching_graph() -> Graph:
    graph = Graph()
    graph.add(
        (
            URIRef(f"{EX}annotation"),
            sample.TARGET_PREDICATE,
            sample.TARGET_OBJECT,
        )
    )
    return graph


def nonmatching_graph() -> Graph:
    graph = Graph()
    graph.add((URIRef(f"{EX}s"), URIRef(f"{EX}p"), URIRef(f"{EX}o")))
    return graph


def install_fake_reader(monkeypatch, records: list[FakeRecord]) -> None:
    FakeRDFDumpReader.calls = []
    FakeRDFDumpReader.records = records
    monkeypatch.setitem(
        __import__("sys").modules,
        "rdf_dump_reader",
        SimpleNamespace(RDFDumpReader=FakeRDFDumpReader),
    )


def read_zip_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zip_file:
        return zip_file.namelist()


def test_extract_sample_uses_rdf_dump_reader_options(monkeypatch, tmp_path) -> None:
    install_fake_reader(monkeypatch, [])
    input_path = tmp_path / "dump"
    input_path.mkdir()

    sample.extract_sample(input_path, tmp_path / "EDM-Sample.zip")

    assert FakeRDFDumpReader.calls == [
        (input_path, "skip_record", "keep"),
    ]


def test_extract_sample_exports_only_matching_records_and_limits_per_subdataset(
    monkeypatch, tmp_path
) -> None:
    install_fake_reader(
        monkeypatch,
        [
            FakeRecord(matching_graph(), "001", "a.rdf"),
            FakeRecord(nonmatching_graph(), "001", "b.rdf"),
            FakeRecord(matching_graph(), "001", "c.rdf"),
            FakeRecord(matching_graph(), "001", "d.rdf"),
            FakeRecord(matching_graph(), "002", "e.rdf"),
        ],
    )
    output_path = tmp_path / "EDM-Sample.zip"

    exported = sample.extract_sample(tmp_path, output_path)

    assert exported == 3
    assert read_zip_names(output_path) == [
        "000001-001-a.rdf",
        "000002-001-c.rdf",
        "000003-002-e.rdf",
    ]
    with zipfile.ZipFile(output_path) as zip_file:
        for name in zip_file.namelist():
            assert b"metadataTierC" in zip_file.read(name)


def test_extract_sample_skips_subdataset_without_match_in_initial_records(
    monkeypatch, tmp_path
) -> None:
    install_fake_reader(
        monkeypatch,
        [
            FakeRecord(nonmatching_graph(), "001", "a.rdf"),
            FakeRecord(nonmatching_graph(), "001", "b.rdf"),
            FakeRecord(matching_graph(), "001", "c.rdf"),
            FakeRecord(matching_graph(), "002", "d.rdf"),
        ],
    )
    output_path = tmp_path / "EDM-Sample.zip"

    exported = sample.extract_sample(
        tmp_path,
        output_path,
        first_record_scan_limit=2,
    )

    assert exported == 1
    assert read_zip_names(output_path) == ["000001-002-d.rdf"]


def test_extract_sample_reports_periodic_progress(monkeypatch, tmp_path) -> None:
    install_fake_reader(
        monkeypatch,
        [
            FakeRecord(matching_graph(), "001", "a.rdf"),
            FakeRecord(nonmatching_graph(), "001", "b.rdf"),
        ],
    )
    times = iter([0.0, 100.0, 300.0])
    progress_updates: list[int] = []

    sample.extract_sample(
        tmp_path,
        tmp_path / "EDM-Sample.zip",
        on_progress=progress_updates.append,
        clock=lambda: next(times),
    )

    assert progress_updates == [1]


def test_sample_main_writes_default_output_and_summary(
    monkeypatch, tmp_path, capsys
) -> None:
    input_path = tmp_path / "dump"
    input_path.mkdir()
    monkeypatch.chdir(tmp_path)

    def fake_extract_sample(path: Path, output_path: Path, **kwargs) -> int:
        assert path == input_path
        assert output_path == Path("EDM-Sample.zip")
        output_path.write_bytes(b"zip placeholder")
        kwargs["on_progress"](2)
        return 2

    monkeypatch.setattr(sample, "extract_sample", fake_extract_sample)

    exit_code = sample.main([str(input_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert (tmp_path / "EDM-Sample.zip").exists()
    assert "Exported records so far: 2" in output
    assert "Exported records: 2" in output
    assert "Output written to: EDM-Sample.zip" in output
