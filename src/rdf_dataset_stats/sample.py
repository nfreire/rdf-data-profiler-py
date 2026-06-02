"""Sample extraction script."""

from __future__ import annotations

import argparse
import logging
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath, Path
from time import monotonic
from typing import Sequence

from rdflib import Graph, URIRef

TARGET_PREDICATE = URIRef("http://www.w3.org/ns/oa#hasBody")
TARGET_OBJECT = URIRef("http://www.europeana.eu/schemas/epf/metadataTierC")
DEFAULT_OUTPUT_PATH = Path("EDM-Sample.zip")


@dataclass(frozen=True)
class SampleRecord:
    subdataset: str
    record_path: str
    data: bytes


def extract_sample(
    input_path: str | Path,
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    *,
    max_records_per_subdataset: int = 2,
    max_records_total: int = 100,
    first_record_scan_limit: int = 100,
    progress_interval_seconds: float = 300.0,
    on_progress: Callable[[int], None] | None = None,
    clock: Callable[[], float] = monotonic,
) -> int:
    """Extract matching records to a sample ZIP file."""
    from rdf_dump_reader import RDFDumpReader

    if max_records_per_subdataset <= 0:
        raise ValueError("max_records_per_subdataset must be greater than zero")
    if max_records_total <= 0:
        raise ValueError("max_records_total must be greater than zero")
    if first_record_scan_limit <= 0:
        raise ValueError("first_record_scan_limit must be greater than zero")

    reader = RDFDumpReader(
        input_path,
        on_parse_error="skip_record",
        invalid_uri_policy="keep",
    )

    selected_records: list[SampleRecord] = []
    exported_records = 0
    current_subdataset: str | None = None
    records_seen_in_subdataset = 0
    matches_seen_in_subdataset = 0
    exported_in_subdataset = 0
    start_time = clock()
    next_progress_time = start_time + progress_interval_seconds

    for record in reader:
        subdataset = str(getattr(record, "subdataset", "unknown"))
        if subdataset != current_subdataset:
            current_subdataset = subdataset
            records_seen_in_subdataset = 0
            matches_seen_in_subdataset = 0
            exported_in_subdataset = 0

        records_seen_in_subdataset += 1

        if _has_required_statement(record.graph):
            matches_seen_in_subdataset += 1
            if exported_in_subdataset < max_records_per_subdataset:
                selected_records.append(_sample_record(record, len(selected_records)))
                exported_records += 1
                exported_in_subdataset += 1

            if exported_records >= max_records_total:
                break

            if exported_in_subdataset >= max_records_per_subdataset:
                _skip_current_subdataset(reader)
        elif (
            records_seen_in_subdataset >= first_record_scan_limit
            and matches_seen_in_subdataset == 0
        ):
            _skip_current_subdataset(reader)

        now = clock()
        if on_progress is not None and now >= next_progress_time:
            on_progress(exported_records)
            if progress_interval_seconds > 0:
                while next_progress_time <= now:
                    next_progress_time += progress_interval_seconds
            else:
                next_progress_time = now

    _write_sample_zip(selected_records, output_path)
    return exported_records


def main(argv: Sequence[str] | None = None) -> int:
    """Run the sample extraction script."""
    _suppress_noisy_rdflib_warnings()
    parser = _build_parser()
    args = parser.parse_args(argv)
    input_path = Path(args.input_option or args.input_path)
    output_path = Path(args.output)

    if not input_path.is_dir():
        print(f"Error: input path is not a directory: {input_path}", file=sys.stderr)
        return 1

    try:
        exported_records = extract_sample(
            input_path,
            output_path,
            on_progress=_print_progress,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Exported records: {exported_records}")
    print(f"Output written to: {output_path}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rdf-dataset-sample",
        description="Extract a sample of EDM records with metadata tier C bodies.",
    )
    parser.add_argument("input_path", nargs="?", help="RDF dump input folder")
    parser.add_argument("--input", dest="input_option", help="RDF dump input folder")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="Sample ZIP output path",
    )
    return parser


def _has_required_statement(graph: Graph) -> bool:
    return (None, TARGET_PREDICATE, TARGET_OBJECT) in graph


def _sample_record(record: object, index: int) -> SampleRecord:
    subdataset = str(getattr(record, "subdataset", "unknown"))
    record_path = str(getattr(record, "record_path", f"record-{index + 1}.rdf"))
    serialized = record.graph.serialize(format="xml")
    if isinstance(serialized, str):
        data = serialized.encode("utf-8")
    else:
        data = bytes(serialized)
    return SampleRecord(subdataset=subdataset, record_path=record_path, data=data)


def _write_sample_zip(records: list[SampleRecord], output_path: str | Path) -> None:
    with zipfile.ZipFile(output_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for index, record in enumerate(records, start=1):
            info = zipfile.ZipInfo(_zip_entry_name(index, record))
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            zip_file.writestr(info, record.data)


def _zip_entry_name(index: int, record: SampleRecord) -> str:
    subdataset = _safe_zip_part(record.subdataset)
    record_name = _safe_zip_part(PurePosixPath(record.record_path).name)
    return f"{index:06d}-{subdataset}-{record_name}"


def _safe_zip_part(value: str) -> str:
    safe_value = "".join(
        char if char.isalnum() or char in {".", "-", "_"} else "_"
        for char in value
    ).strip("._")
    return safe_value or "record"


def _skip_current_subdataset(reader: object) -> None:
    skip_subdataset = getattr(reader, "skip_subdataset", None)
    if callable(skip_subdataset):
        skip_subdataset()


def _print_progress(exported_records: int) -> None:
    print(f"Exported records so far: {exported_records}")


def _suppress_noisy_rdflib_warnings() -> None:
    logging.getLogger("rdflib.term").setLevel(logging.CRITICAL)


if __name__ == "__main__":
    raise SystemExit(main())
