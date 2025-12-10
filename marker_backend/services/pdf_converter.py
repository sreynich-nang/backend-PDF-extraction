"""PDF to image conversion service.

Converts PDF files to individual page images, processes each with marker_single,
and combines extracted content into a single markdown output.
"""

from pathlib import Path
from typing import List, Tuple
import tempfile
import shutil
from ..core.config import TEMP_DIR, OUTPUTS_DIR, PDF2IMAGE_DIR
from ..core.logger import get_logger
from ..core.exceptions import MarkerError

logger = get_logger(__name__)


def _convert_pdf_to_images(pdf_path: Path, output_dir: Path) -> List[Path]:
    """Convert PDF to individual page images (PNG).
    
    Uses PyMuPDF (fitz) which is self-contained and doesn't require external system dependencies.
    
    Args:
        pdf_path: Path to input PDF file
        output_dir: Directory to save extracted images
    
    Returns:
        List of Path objects for generated image files (sorted by page number)
    
    Raises:
        MarkerError: If conversion fails
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise MarkerError(
            "PyMuPDF library not installed. Install with: pip install PyMuPDF"
        )
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        logger.info(f"Converting PDF to images: {pdf_path}")
        
        # Open PDF document
        doc = fitz.open(str(pdf_path))
        page_count = doc.page_count
        logger.info(f"PDF has {page_count} pages")
        
        image_paths = []
        
        for page_num in range(page_count):
            # Get page and render to image (pixmap)
            page = doc[page_num]
            # Render at 2.0 zoom for 200 DPI equivalent quality
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            
            # Save page as PNG
            image_filename = output_dir / f"{pdf_path.stem}_page_{page_num + 1:04d}.png"
            pix.save(str(image_filename))
            image_paths.append(image_filename)
            logger.debug(f"Saved page {page_num + 1} to {image_filename}")
        
        doc.close()
        logger.info(f"Successfully converted {len(image_paths)} pages from PDF")
        return image_paths
    
    except Exception as e:
        logger.error(f"PDF to image conversion failed: {e}")
        raise MarkerError(f"Failed to convert PDF to images: {str(e)}")


def _process_image_with_marker(image_path: Path, output_dir: Path) -> str:
    """Process single image with marker_single and return extracted markdown content.
    
    Args:
        image_path: Path to image file
        output_dir: Directory where marker should save outputs
    
    Returns:
        Extracted markdown content as string
    
    Raises:
        MarkerError: If marker processing fails
    """
    from .marker_runner import run_marker_for_chunk
    
    try:
        logger.info(f"Processing image with marker_single: {image_path}")
        output_path = run_marker_for_chunk(image_path, output_dir=output_dir)
        
        # Read the markdown output
        if not output_path.exists():
            raise MarkerError(f"Marker output not found at {output_path}")
        
        with output_path.open("r", encoding="utf-8") as f:
            content = f.read()
        
        logger.debug(f"Extracted {len(content)} characters from {image_path}")
        return content
    
    except MarkerError:
        raise
    except Exception as e:
        logger.error(f"Error processing image {image_path}: {e}")
        raise MarkerError(f"Failed to process image with marker: {str(e)}")


def _combine_markdown_content(
    contents: List[Tuple[Path, str]],
    original_filename: str
) -> str:
    """Combine extracted markdown content from all pages.
    
    Args:
        contents: List of tuples (image_path, markdown_content)
        original_filename: Name of original PDF file for reference
    
    Returns:
        Combined markdown content with page separators and metadata
    """
    combined = f"# Document: {original_filename}\n\n"
    combined += f"*Converted and processed {len(contents)} pages*\n\n"
    combined += "---\n\n"
    
    for image_path, content in contents:
        # Extract page number from filename (e.g., "document_page_0001.png" -> "1")
        page_num = image_path.stem.split("_page_")[-1]
        combined += f"## Page {page_num}\n\n"
        combined += content
        combined += "\n\n---\n\n"
    
    return combined


def _save_combined_markdown(content: str, output_path: Path) -> Path:
    """Save combined markdown content to file.
    
    Args:
        content: Combined markdown content
        output_path: Path where to save the file
    
    Returns:
        Path to saved file
    
    Raises:
        MarkerError: If file write fails
    """
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Saved combined markdown to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to save markdown output: {e}")
        raise MarkerError(f"Failed to save combined markdown: {str(e)}")


def _cleanup_temp_images(image_paths: List[Path], keep_images: bool = False):
    """Clean up temporary image files after processing.
    
    Args:
        image_paths: List of image paths to delete
        keep_images: If True, preserve images; otherwise delete them
    """
    if keep_images:
        logger.info("Preserving temporary image files (keep_images=True)")
        return
    
    for image_path in image_paths:
        try:
            if image_path.exists():
                image_path.unlink()
                logger.debug(f"Deleted temporary image: {image_path}")
        except Exception as e:
            logger.warning(f"Failed to delete temporary image {image_path}: {e}")


def convert_pdf_and_process(
    pdf_path: Path,
    output_dir: Path = None,
    keep_images: bool = False,
    temp_image_subdir: str = None
) -> Path:
    """Main workflow: convert PDF to images, process each with marker_single, combine results.
    
    Outputs are organized hierarchically:
    - OUTPUTS_DIR/{pdf_filename}/
        - {pdf_filename}.md (combined markdown)
        - {pdf_filename}_page_0001/
            - {pdf_filename}_page_0001.md
            - {pdf_filename}_page_0001_meta.json
        - {pdf_filename}_page_0002/
            - ...
    
    Args:
        pdf_path: Path to input PDF file
        output_dir: Directory for document folder (defaults to OUTPUTS_DIR)
        keep_images: If True, preserve extracted images in PDF2IMAGE_DIR; otherwise delete after processing
        temp_image_subdir: Subdirectory in PDF2IMAGE_DIR for intermediate images 
                          (defaults to "{pdf_stem}_images")
    
    Returns:
        Path to final combined markdown file
    
    Raises:
        MarkerError: If any step in the workflow fails
    """
    if output_dir is None:
        output_dir = OUTPUTS_DIR
    
    if temp_image_subdir is None:
        temp_image_subdir = f"{pdf_path.stem}_images"
    
    # Images stored in PDF2IMAGE_DIR instead of TEMP_DIR
    temp_image_dir = PDF2IMAGE_DIR / temp_image_subdir
    # Document-specific output folder
    doc_output_dir = output_dir / pdf_path.stem
    image_paths = []  # Initialize to prevent UnboundLocalError in except block
    
    try:
        # Step 1: Convert PDF to images
        logger.info(f"Starting PDF conversion workflow for {pdf_path}")
        image_paths = _convert_pdf_to_images(pdf_path, temp_image_dir)
        
        if not image_paths:
            raise MarkerError(f"No images extracted from PDF {pdf_path}")
        
        logger.info(f"Extracted {len(image_paths)} images from PDF")
        
        # Step 2: Process each image with marker_single (sequentially)
        logger.info("Processing extracted images with marker_single")
        contents: List[Tuple[Path, str]] = []
        
        # Ensure document output directory exists before processing
        doc_output_dir.mkdir(parents=True, exist_ok=True)
        
        for idx, image_path in enumerate(image_paths, 1):
            logger.info(f"Processing image {idx}/{len(image_paths)}: {image_path.name}")
            try:
                markdown_content = _process_image_with_marker(image_path, output_dir=doc_output_dir)
                contents.append((image_path, markdown_content))
            except MarkerError as e:
                logger.warning(f"Failed to process image {image_path}: {e}")
                # Continue with remaining images instead of failing completely
                contents.append((image_path, f"*Failed to extract content from this page: {str(e)}*\n"))
        
        # Step 3: Combine all extracted content
        logger.info(f"Combining content from {len(contents)} processed images")
        combined_content = _combine_markdown_content(contents, pdf_path.name)
        
        # Step 4: Save combined markdown inside document folder
        output_path = doc_output_dir / f"{pdf_path.stem}.md"
        final_path = _save_combined_markdown(combined_content, output_path)
        
        # Step 5: Cleanup temporary images (if not keeping)
        _cleanup_temp_images(image_paths, keep_images=keep_images)
        
        logger.info(f"PDF conversion workflow completed successfully. Output: {final_path}")
        return final_path
    
    except MarkerError:
        # Cleanup on error
        _cleanup_temp_images(image_paths, keep_images=keep_images)
        raise
    except Exception as e:
        # Cleanup on unexpected error
        logger.error(f"Unexpected error in PDF conversion workflow: {e}")
        _cleanup_temp_images(image_paths, keep_images=False)
        raise MarkerError(f"PDF conversion workflow failed: {str(e)}")
