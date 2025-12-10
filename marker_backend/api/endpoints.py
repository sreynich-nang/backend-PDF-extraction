from fastapi import APIRouter, UploadFile, File, HTTPException    
from fastapi.responses import FileResponse    
from ..core.logger import get_logger    
from ..core.config import ensure_dirs, UPLOADS_DIR, OUTPUTS_DIR, FILTERS_DIR  
from ..services.file_handler import save_upload    
from ..services.marker_runner import run_marker_for_chunk    
from ..services.pdf_converter import convert_pdf_and_process
from ..models.schemas import UploadResponse, TableExtractionResponse    
from ..core.exceptions import InvalidFileError, MarkerError  # Removed ChunkingError  
from pathlib import Path
import time    
    
router = APIRouter()    
logger = get_logger(__name__)    
    
    
@router.post("/upload", response_model=UploadResponse)    
async def upload_pdf(file: UploadFile = File(...)):    
    """Upload a PDF or image and process it with marker.
    
    For PDFs: Converts to images, processes each page with marker_single, combines output.
    For images: Processes directly with marker_single.
    """
    ensure_dirs()    
    start = time.time()    
    try:    
        saved_path = await save_upload(file)    
        logger.info(f"Saved upload to {saved_path}")
        
        # Check file type
        file_suffix = saved_path.suffix.lower()
        
        if file_suffix == ".pdf":
            # Use PDF converter workflow for PDFs
            logger.info(f"PDF detected, using conversion workflow: {saved_path}")
            output = convert_pdf_and_process(saved_path, output_dir=OUTPUTS_DIR, keep_images=False)
        else:
            # Direct processing for images - organize by filename in outputs
            logger.info(f"Image detected, processing directly with marker_single: {saved_path}")
            # Create a directory for this image's output (similar to PDF structure)
            img_output_dir = OUTPUTS_DIR / saved_path.stem
            img_output_dir.mkdir(parents=True, exist_ok=True)
            output = run_marker_for_chunk(saved_path, output_dir=img_output_dir)
        
        logger.info(f"Processing produced output file: {output}")    
    
        elapsed = time.time() - start    
    
        return UploadResponse(    
            status="success",    
            filename=saved_path.name,    
            merged_path=str(output),  
            processing_time_seconds=round(elapsed, 2),    
        )    
    
    except InvalidFileError as e:    
        logger.exception("Invalid file error")    
        raise HTTPException(status_code=400, detail=str(e))    
    except MarkerError as e:    
        logger.exception("Marker processing error")    
        raise HTTPException(status_code=500, detail=str(e))    
    except Exception as e:    
        logger.exception("Unexpected error processing upload")    
        raise HTTPException(status_code=500, detail=str(e))    
    
    
@router.get("/download/{filename:path}")    
def download(filename: str):    
    path = OUTPUTS_DIR / filename  
    if not path.exists():    
        raise HTTPException(status_code=404, detail="File not found")    
    return FileResponse(path, filename=path.name, media_type="text/markdown")


@router.post("/filter_tables", response_model=TableExtractionResponse)
async def filter_tables(document: str, sheets_per_file: int = 30, store_in_filters: bool = False):
    """Extract tables from a processed document's markdown and save Excel batches.

    Expects marker output folder structure: outputs/<document>/<document>.md
    Returns metadata including created Excel files.
    """
    ensure_dirs()
    start = time.time()
    try:
        from ..services.table_extractor import extract_and_save_tables
        excel_base_dir = FILTERS_DIR if store_in_filters else None
        md_path, dfs, excel_files, excel_folder = extract_and_save_tables(
            document,
            OUTPUTS_DIR,
            sheets_per_file=sheets_per_file,
            excel_base_dir=excel_base_dir,
        )
        logger.info(f"Extracted {len(dfs)} tables for document '{document}' into {excel_folder}")
        return TableExtractionResponse(
            status="success",
            document=document,
            markdown_path=str(md_path),
            tables_count=len(dfs),
            excel_folder=str(excel_folder),
            excel_files=[str(p) for p in excel_files],
        )
    except FileNotFoundError as e:
        logger.exception("Markdown file not found for table extraction")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("Unexpected error during table extraction")
        raise HTTPException(status_code=500, detail=str(e))
