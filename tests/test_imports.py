def test_package_imports() -> None:
    import rdf_dataset_stats
    import rdf_dataset_stats.cli
    import rdf_dataset_stats.collector
    import rdf_dataset_stats.excel
    import rdf_dataset_stats.model
    import rdf_dataset_stats.sample

    assert rdf_dataset_stats.__version__ == "0.1.0"
