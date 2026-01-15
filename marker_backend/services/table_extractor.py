import re
from pathlib import Path
from typing import List, Tuple, Optional
import pandas as pd
import logging

# Fallback logger if not using your package
def get_logger(name: str):
    logger = logging.getLogger(name)
    if not logger.hasHandlers():
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

logger = get_logger(__name__)

def extract_tables_as_dataframes(markdown_path: Path) -> List[pd.DataFrame]:
    """Extract all markdown tables from a file into a list of DataFrames."""
    content = markdown_path.read_text(encoding="utf-8")
    
    # Regex to match lines starting with | and ending with |
    table_pattern = r"^\|(.+)\|$"
    lines = content.split("\n")
    
    tables: List[pd.DataFrame] = []
    current_table_lines: List[str] = []
    in_table = False
    
    for line in lines:
        if re.match(table_pattern, line.strip()):
            in_table = True
            current_table_lines.append(line)
        elif in_table and line.strip():
            if not re.match(table_pattern, line.strip()):
                # End of table
                if current_table_lines:
                    df = _parse_markdown_table(current_table_lines)
                    if df is not None and len(df) > 0:
                        tables.append(df)
                current_table_lines = []
                in_table = False
        elif in_table and not line.strip():
            # Empty line might still be in table
            pass
    
    # Add last table if file ends with a table
    if current_table_lines:
        df = _parse_markdown_table(current_table_lines)
        if df is not None and len(df) > 0:
            tables.append(df)
    
    return tables


def _parse_markdown_table(lines: List[str]) -> Optional[pd.DataFrame]:
    """Parse markdown table lines into a pandas DataFrame."""
    if len(lines) < 2:
        return None
    
    # Header
    header_line = lines[0]
    headers = [h.strip() for h in header_line.split("|")[1:-1]]
    
    # Skip separator (usually second line) and read data
    data_rows: List[List[str]] = []
    for line in lines[2:]:
        if not line.strip():
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) == len(headers):
            data_rows.append(cells)
    
    if not data_rows:
        return None
    
    df = pd.DataFrame(data_rows, columns=headers)
    return df


def save_tables_as_csv(
    dfs: List[pd.DataFrame],
    md_file_path: Path,
    output_dir: Path,
) -> List[Path]:
    """Save each DataFrame as a separate CSV file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    created: List[Path] = []
    
    if not dfs:
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
    csv_base_dir: Optional[Path] = None,
) -> Tuple[Path, List[pd.DataFrame], List[Path], Path]:
    """Extract tables from markdown and save them as CSVs."""
    possible_paths = [
        outputs_dir / document_name / f"{document_name}.md",
        outputs_dir / document_name / document_name / f"{document_name}.md",
        outputs_dir / f"{document_name}.md",
    ]
    
    md_path: Optional[Path] = None
    for path in possible_paths:
        if path.exists():
            md_path = path
            break
    
    if md_path is None:
        raise FileNotFoundError(
            f"Processed markdown not found for document '{document_name}'. "
            f"Searched paths: {possible_paths}"
        )

    dfs = extract_tables_as_dataframes(md_path)
    
    csv_folder = csv_base_dir / document_name if csv_base_dir else outputs_dir / document_name / f"tables_csv_{document_name}"
    csv_files = save_tables_as_csv(dfs, md_path, csv_folder)
    
    return md_path, dfs, csv_files, csv_folder
