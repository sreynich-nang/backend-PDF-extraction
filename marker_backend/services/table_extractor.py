import re
from pathlib import Path
from io import StringIO
from typing import List
import pandas as pd

from ..core.logger import get_logger

logger = get_logger(__name__)

TABLE_REGEX = re.compile(r"(\|.*\|\s*\n)+", re.MULTILINE)
SEPARATOR_LINE_REGEX = re.compile(r'^\s*\|?\s*:?-{3,}', re.IGNORECASE)


def extract_tables_as_dataframes(md_file_path: Path) -> List[pd.DataFrame]:
    """Extract markdown tables from a file and convert them into DataFrames.

    Returns a list of DataFrames. Any table that fails to parse is skipped.
    """
    if not md_file_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_file_path}")

    content = md_file_path.read_text(encoding="utf-8")
    tables_md = [m.group(0) for m in TABLE_REGEX.finditer(content)]

    dataframes: List[pd.DataFrame] = []
    for table_md in tables_md:
        cleaned_table = "\n".join(
            line for line in table_md.splitlines()
            if not SEPARATOR_LINE_REGEX.match(line)
        ).strip()
        if not cleaned_table:
            continue
        try:
            df = pd.read_csv(StringIO(cleaned_table), sep="|", engine="python")
            df = df.dropna(axis=1, how="all")
            df.columns = df.columns.str.strip()
            df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
            dataframes.append(df)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to parse a table chunk: {e}")
            continue
    logger.info(f"Extracted {len(dataframes)} tables from {md_file_path.name}")
    return dataframes


def save_tables_as_csv(
    dfs: List[pd.DataFrame],
    md_file_path: Path,
    output_dir: Path,
) -> List[Path]:
    """Save each DataFrame as a separate CSV file.

    Files are written into `output_dir` which is created if absent.
    One CSV file per table: table_1.csv, table_2.csv, etc.
    Returns list of created CSV file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    created: List[Path] = []
    total = len(dfs)
    if total == 0:
        logger.info("No tables to save; skipping CSV generation.")
        return created

    for idx, df in enumerate(dfs, start=1):
        csv_path = output_dir / f"table_{idx}.csv"
        df.to_csv(csv_path, index=False, encoding="utf-8")
        created.append(csv_path)
        logger.info(f"Created CSV file: {csv_path}")
    return created


def extract_and_save_tables(
    document_name: str,
    outputs_dir: Path,
    csv_base_dir: Path | None = None,
):
    """High-level helper to extract tables for a processed document and save them as CSV.

    Marker output markdown expected at: outputs_dir / document_name / document_name.md
    If csv_base_dir provided, CSV files stored under csv_base_dir / document_name.
    Otherwise defaults to outputs_dir / document_name / tables_csv_<document_name>.
    Returns tuple (markdown_path, tables_list, csv_files_list, csv_folder_path)
    """
    md_path = outputs_dir / document_name / f"{document_name}.md"
    if not md_path.exists():
        raise FileNotFoundError(f"Processed markdown not found for document '{document_name}': {md_path}")

    dfs = extract_tables_as_dataframes(md_path)
    if csv_base_dir:
        csv_folder = csv_base_dir / document_name
    else:
        csv_folder = outputs_dir / document_name / f"tables_csv_{document_name}"
    csv_files = save_tables_as_csv(dfs, md_path, csv_folder)
    return md_path, dfs, csv_files, csv_folder
