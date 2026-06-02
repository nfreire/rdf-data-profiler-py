# RDF Dataset Statistics Application - Specification

## 1. Purpose

Build a Python application that reads a record-based RDF dataset dump using `rdf-dump-reader` and produces class/property usage statistics in an `.xlsx` spreadsheet.

The application analyzes RDF records as independent graphs and aggregates statistics across the full dump.

## 2. Dependency Boundary

This project MUST use `rdf-dump-reader` as the only mechanism for reading RDF dump ZIP files and RDF/XML records.

The application MUST NOT:

* Traverse ZIP files directly
* Read RDF/XML files directly from ZIP archives
* Reimplement RDF/XML parsing
* Reimplement dump iteration logic

The application MUST import and use:

```python
from rdf_dump_reader import RDFDumpReader
```

Expected reader behavior:

* One `Record` is yielded per successfully parsed RDF/XML record
* `Record.graph` is an `rdflib.Graph`
* RDF/XML parse errors are skipped by default by the reader
* Invalid URI references are preserved when RDFLib can parse the record

## 3. Scope

### 3.1 In scope

* Reading an RDF dump from a local filesystem folder using `rdf-dump-reader`
* Iterating over records as `rdflib.Graph` instances
* Collecting aggregate statistics by RDF class
* Counting class usage
* Counting property usage per class
* Distinguishing property usage with literal values and resource values
* Determining the RDF class(es) of resource values using `rdf:type`
* Counting resource values without explicit `rdf:type` as `rdfs:Resource`
* Writing the aggregated statistics to an `.xlsx` spreadsheet
* Creating one spreadsheet sheet per RDF class

### 3.2 Out of scope

* RDF validation
* RDF transformation or normalization
* Reasoning or inferencing
* Dereferencing URIs
* Merging records into one persistent RDF store
* Generating visualizations
* Interactive UI
* Database storage

## 4. Input

The application input is:

* A local filesystem folder containing the RDF dump
* An output `.xlsx` file path

The RDF dump folder MUST be passed to `RDFDumpReader`.

## 5. RDF Data Model Assumptions

The input dataset is record-based.

Each record is represented by one `rdflib.Graph`.

The application MUST process each record independently, but aggregate statistics globally across all records.

A resource may have zero, one, or multiple `rdf:type` statements within the same record graph.

No cross-record lookup is required. If a resource is used as an object in one record but has its `rdf:type` only in another record, the application MUST NOT attempt to resolve that type across records unless this specification is later extended.

## 6. Statistics to Collect

### 6.1 Class usage

For each RDF class `C`, count how many times `C` is used in `rdf:type` statements.

Definition:

```turtle
?s rdf:type C .
```

Each matching triple increments the usage count for class `C` by 1.

If the same subject has the same `rdf:type` class multiple times in the same record graph, each triple SHOULD be counted as one occurrence, following RDF graph semantics. Since RDF graphs do not contain duplicate triples, duplicate serialized statements collapsed by RDFLib will count once.

### 6.2 Property usage per subject class

For each subject resource `S` having RDF class `C`:

```turtle
S rdf:type C .
S P O .
```

The application MUST count usage of property `P` under class `C`.

The `rdf:type` property itself SHOULD be excluded from property usage statistics unless explicitly configured otherwise.

If subject `S` has multiple RDF classes, the property usage MUST be counted once under each subject class.

Example:

```turtle
:S rdf:type :ClassA .
:S rdf:type :ClassB .
:S :title "Title" .
```

The property `:title` is counted under both `:ClassA` and `:ClassB`.

### 6.3 Literal object counts

If object `O` is an RDF literal:

```turtle
S P "literal" .
```

Then increment the literal count for property `P` under subject class `C`.

Literal values include language-tagged strings and datatyped literals.

### 6.4 Resource object counts

If object `O` is a resource, meaning an `rdflib.URIRef` or `rdflib.BNode`:

```turtle
S P O .
```

Then the application MUST determine the RDF type(s) of `O` within the same record graph.

For each object class `OC` found through:

```turtle
O rdf:type OC .
```

increment the resource count for property `P`, subject class `C`, and object class `OC`.

If no `rdf:type` statement is present for `O` in the same record graph, count the object as:

```text
http://www.w3.org/2000/01/rdf-schema#Resource
```

That is, `rdfs:Resource`.

If object `O` has multiple RDF classes, each object class MUST be counted separately.

Example:

```turtle
:S rdf:type :C .
:S :related :O .
:O rdf:type :A .
:O rdf:type :B .
```

For class `:C` and property `:related`, increment:

* resource count for object class `:A`
* resource count for object class `:B`

### 6.5 Untyped subjects

Property usage statistics are collected per RDF class.

If a subject has no `rdf:type` statement, its properties MUST NOT be included in class-specific property statistics.

However, the subject may still be counted as an object value of another property using `rdfs:Resource` if it has no type as an object.

## 7. Aggregation Model

The application MUST maintain aggregate counters across all records.

Recommended internal structure:

```python
stats[class_uri].class_count
stats[class_uri].properties[property_uri].literal_count
stats[class_uri].properties[property_uri].resource_counts[object_class_uri]
```

Where:

* `class_uri` is the subject class URI
* `property_uri` is the property URI
* `object_class_uri` is the RDF class URI of a resource object, or `rdfs:Resource`

Blank node classes SHOULD be supported if present as `rdf:type` objects, but output should serialize them using their RDFLib string representation.

## 8. Output

The application MUST write an `.xlsx` spreadsheet.

### 8.1 Workbook structure

The workbook MUST contain one sheet per RDF class.

Each sheet represents statistics for one subject RDF class.

The sheet name SHOULD be derived from the RDF class URI using a safe, human-readable shortening strategy.

Because Excel sheet names are limited, the implementation MUST ensure valid unique sheet names.

Requirements:

* Sheet names MUST be no longer than 31 characters
* Sheet names MUST NOT contain Excel-invalid characters: `:`, `\`, `/`, `?`, `*`, `[`, `]`
* If two classes produce the same sheet name, suffixes MUST be added to make them unique

### 8.2 Sheet content

Each class sheet MUST include:

* The full RDF class URI
* The class usage count
* A table of property statistics

Recommended layout:

```text
Class URI: <full class URI>
Class count: <count>

Property URI | Literal count | Resource object class URI | Resource count
```

For each property:

* There MUST be one row for the literal count
* There MUST be one row per resource object class count

Suggested row representation:

```text
Property URI | Literal count | Resource object class URI | Resource count
<property>   | 12            |                            |
<property>   |               | <object class URI>          | 5
<property>   |               | rdfs:Resource               | 3
```

Alternative tabular layouts are acceptable if they preserve all required information unambiguously.

### 8.3 Ordering in output

Output MUST be deterministic.

* Class sheets MUST be ordered lexicographically by full class URI before applying Excel-safe sheet naming
* Properties within each sheet MUST be ordered lexicographically by full property URI
* Resource object classes for each property MUST be ordered lexicographically by full object class URI

### 8.4 Intermediate output

For long-running dumps, the application MUST write intermediate results to the configured output `.xlsx` file after every 1,000,000 records processed.

Intermediate output MUST use the same workbook structure, sheet naming rules, and deterministic ordering as the final output.

The final output file MUST still be written after processing completes, even if the total number of processed records is not an exact multiple of 1,000,000.

## 9. Command-Line Interface

The application SHOULD provide a command-line interface.

Recommended usage:

```bash
rdf-dataset-stats /path/to/dump output.xlsx
```

Equivalent long options MAY be provided:

```bash
rdf-dataset-stats --input /path/to/dump --output output.xlsx
```

The CLI MUST:

* Accept an input dump folder
* Accept an output `.xlsx` path
* Exit with non-zero status on unrecoverable errors
* Print a concise summary when processing completes

Recommended summary:

```text
Processed records: <n>
Classes found: <n>
Output written to: <path>
```

### 9.1 Progress reporting

While processing a dump, the application MUST print the name of the subdataset that is currently being processed.

At least once every 5 minutes during processing, the application MUST print a concise progress update containing:

* Total records processed so far
* Average records processed per second since processing started
* Estimated time required to process 1,000,000 records at the current average speed

The estimated time for 1,000,000 records MUST be formatted as:

```text
hh:mm:ss
```

## 10. Error Handling

### 10.1 Input errors

If the input folder does not exist or is not a directory, the application MUST fail with a clear error.

### 10.2 Output errors

If the output `.xlsx` file cannot be written, the application MUST fail with a clear error.

### 10.3 RDF parse errors

RDF parse errors are handled by `rdf-dump-reader`.

By default, the application SHOULD instantiate the reader as:

```python
reader = RDFDumpReader(
    input_path,
    on_parse_error="skip_record",
    invalid_uri_policy="keep",
)
```

The application SHOULD NOT add separate RDF/XML parsing error handling unless needed to wrap user-facing error messages.

## 11. Sampling Script

The project MUST provide an additional script, independent from the statistics CLI, that extracts a sample of RDF records.

The sampling script MUST read records through `rdf-dump-reader` and MUST NOT traverse ZIP files directly or parse RDF/XML directly.

The sample MUST include only records whose graph contains this RDF statement:

```turtle
?s <http://www.w3.org/ns/oa#hasBody> <http://www.europeana.eu/schemas/epf/metadataTierC> .
```

The sampling script MUST extract a maximum of 2 matching records per subdataset. The script MUST skip the rest of that subdataset after 2 matching records are extracted.

When processing a subdataset, if no record containing the required statement is found within the first 100 records for that subdataset, the script MUST skip the rest of that subdataset.

The sampling script MUST extract a maximum of 100 matching records. After that the remaider of the dataset must be skiped.

At least once every 5 minutes during sampling, the script MUST print the total number of records exported so far.

The sampling script MUST write the resulting sample to:

```text
EDM-Sample.zip
```

The output ZIP MUST contain the selected records in a deterministic order.

## 12. Dependencies and Packaging

### 12.1 Runtime dependencies

* Python >= 3.10
* `rdf-dump-reader`
* `rdflib >= 7.0`
* `openpyxl`

### 12.2 Development dependencies

* `pytest`

### 12.3 Packaging

The project SHOULD use `pyproject.toml`.

The CLI entry point SHOULD be declared using project scripts, for example:

```toml
[project.scripts]
rdf-dataset-stats = "rdf_dataset_stats.cli:main"
```

The sampling script entry point SHOULD be declared using project scripts, for example:

```toml
[project.scripts]
rdf-dataset-sample = "rdf_dataset_stats.sample:main"
```

## 13. Testing Requirements

The test suite MUST use `pytest`.

Tests MUST use small fixture dumps stored under:

```text
tests/data/
```

Tests MUST cover:

* Reading records through `RDFDumpReader`
* Counting RDF class usage
* Counting literal property usage per subject class
* Counting resource property usage per subject class and object class
* Counting resource objects without type as `rdfs:Resource`
* Counting resource objects with multiple RDF classes separately
* Subjects with multiple RDF classes contributing property counts to each class
* Excluding untyped subjects from class-specific property statistics
* Excluding `rdf:type` from property statistics by default
* Deterministic ordering of output data
* Writing an `.xlsx` file
* Writing intermediate `.xlsx` results after every 1,000,000 processed records
* Creating one worksheet per class
* Valid and unique Excel sheet names
* CLI invocation with input and output paths
* CLI progress reporting, including current subdataset name and periodic throughput estimates
* Sampling script selection of records containing the required `oa:hasBody` metadata tier statement
* Sampling script limit of 2 exported records per subdataset
* Sampling script skip behavior when no matching record appears in the first 100 records of a subdataset
* Sampling script periodic exported-record progress reporting
* Sampling script writing `EDM-Sample.zip`

## 14. Suggested Module Structure

```text
src/rdf_dataset_stats/
    __init__.py
    cli.py
    model.py
    collector.py
    excel.py
```

Suggested responsibilities:

* `model.py`: dataclasses for counters/statistics
* `collector.py`: RDF graph analysis and aggregation logic
* `excel.py`: spreadsheet writing
* `cli.py`: command-line argument parsing and orchestration
* `sample.py`: sample extraction script

## 15. Acceptance Criteria

The implementation is acceptable when:

* The application reads an RDF dump only through `rdf-dump-reader`
* It aggregates class/property statistics across all successfully parsed records
* It correctly distinguishes literal and resource property values
* It counts resource object classes using `rdf:type` from the same record graph
* It counts untyped resource objects as `rdfs:Resource`
* It writes a deterministic `.xlsx` workbook
* Each RDF class has its own worksheet
* Tests cover the required statistics and output behavior
* The sampling script writes `EDM-Sample.zip` containing only selected matching records
