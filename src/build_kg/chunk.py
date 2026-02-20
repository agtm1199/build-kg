#!/usr/bin/env python3
"""
Simple document chunker using Unstructured open source library.
Processes PDF and MD files from input directory and saves chunks to output directory.
No API key required - runs entirely locally.
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from unstructured.partition.md import partition_md

try:
    from unstructured.partition.pdf import partition_pdf
except ImportError:
    partition_pdf = None
from unstructured.chunking.basic import chunk_elements
from unstructured.chunking.title import chunk_by_title


# ANSI color codes for fancy logging
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    # Colors
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'

    # Background
    BG_BLUE = '\033[44m'
    BG_GREEN = '\033[42m'


def log_header(message: str) -> None:
    """Print a prominent header message."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{message}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}\n")


def log_step(step: str, message: str, status: str = "info") -> None:
    """Log a processing step with visual indicators."""
    icon_map = {
        "info": f"{Colors.BLUE}ℹ{Colors.RESET}",
        "success": f"{Colors.GREEN}✓{Colors.RESET}",
        "warning": f"{Colors.YELLOW}⚠{Colors.RESET}",
        "error": f"{Colors.RED}✗{Colors.RESET}",
        "processing": f"{Colors.MAGENTA}➜{Colors.RESET}",
        "arrow": f"{Colors.CYAN}→{Colors.RESET}",
    }
    icon = icon_map.get(status, "•")
    print(f"{icon} {Colors.BOLD}[{step}]{Colors.RESET} {message}")


def log_detail(message: str, indent: int = 2) -> None:
    """Log a detailed message with indentation."""
    print(f"{' '*indent}{Colors.DIM}{message}{Colors.RESET}")


def log_metric(label: str, value: Any, unit: str = "") -> None:
    """Log a metric with label and value."""
    print(f"  {Colors.CYAN}{label}:{Colors.RESET} {Colors.BOLD}{value}{Colors.RESET}{unit}")


def format_time(seconds: float) -> str:
    """Format time duration in human-readable format."""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.2f}s"
    else:
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}m {secs:.1f}s"


def make_serializable(obj: Any) -> Any:
    """
    Convert any object to a JSON-serializable format.
    Handles complex objects like PixelSpace and other non-serializable types.

    Args:
        obj: Object to convert

    Returns:
        JSON-serializable version of the object
    """
    # Handle None, primitives, and strings
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj

    # Handle lists and tuples
    if isinstance(obj, (list, tuple)):
        return [make_serializable(item) for item in obj]

    # Handle dictionaries
    if isinstance(obj, dict):
        return {key: make_serializable(value) for key, value in obj.items()}

    # Handle objects with __dict__ attribute (convert to dictionary)
    if hasattr(obj, '__dict__'):
        return make_serializable(obj.__dict__)

    # Handle objects with to_dict method
    if hasattr(obj, 'to_dict') and callable(obj.to_dict):
        try:
            return make_serializable(obj.to_dict())
        except Exception:
            pass

    # For any other object, try to convert to string
    try:
        return str(obj)
    except Exception:
        return f"<{type(obj).__name__} object>"


def get_file_path_with_parents(file_path, num_parents=2):
    """
    Get file path including up to num_parents parent directories.

    Args:
        file_path: Path object of the file
        num_parents: Number of parent directories to include

    Returns:
        String path like /parent1/parent2/filename
    """
    parts = file_path.parts
    # Get the last (num_parents + 1) parts (parents + filename)
    relevant_parts = parts[-(num_parents + 1):] if len(parts) > num_parents else parts
    return "/" + "/".join(relevant_parts)


def calculate_fingerprint(text):
    """
    Calculate a fingerprint (hash) of normalized text for deduplication.

    Args:
        text: The text to fingerprint

    Returns:
        SHA256 hash of normalized text
    """
    # Normalize: lowercase, remove extra whitespace
    normalized = ' '.join(text.lower().split())
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()


def extract_coordinates(chunk):
    """
    Extract coordinates from original elements in a chunk.
    Ensures all coordinate data is JSON-serializable.

    Args:
        chunk: Chunk element with metadata

    Returns:
        List of coordinate dictionaries or None
    """
    coordinates = []
    if hasattr(chunk, 'metadata') and hasattr(chunk.metadata, 'orig_elements'):
        for element in chunk.metadata.orig_elements:
            if hasattr(element, 'metadata') and hasattr(element.metadata, 'coordinates'):
                coord = element.metadata.coordinates
                if coord:
                    # Use make_serializable to handle complex objects like PixelSpace
                    coord_dict = {
                        'points': make_serializable(coord.points if hasattr(coord, 'points') else None),
                        'system': make_serializable(coord.system if hasattr(coord, 'system') else None),
                        'layout_width': make_serializable(
                            coord.layout_width if hasattr(coord, 'layout_width') else None),
                        'layout_height': make_serializable(
                            coord.layout_height if hasattr(coord, 'layout_height') else None),
                    }
                    coordinates.append(coord_dict)
    return coordinates if coordinates else None


def extract_detection_class_prob(chunk):
    """
    Extract detection class probability from original elements.

    Args:
        chunk: Chunk element with metadata

    Returns:
        List of probabilities or None
    """
    probabilities = []
    if hasattr(chunk, 'metadata') and hasattr(chunk.metadata, 'orig_elements'):
        for element in chunk.metadata.orig_elements:
            if hasattr(element, 'metadata') and hasattr(element.metadata, 'detection_class_prob'):
                prob = element.metadata.detection_class_prob
                if prob is not None:
                    probabilities.append(prob)
    return probabilities if probabilities else None


def determine_chunk_position(chunk_index, total_chunks):
    """
    Determine the position of a chunk in the document.

    Args:
        chunk_index: Current chunk index (1-based)
        total_chunks: Total number of chunks

    Returns:
        Position string: 'first', 'middle', 'last', or 'only'
    """
    if total_chunks == 1:
        return 'only'
    elif chunk_index == 1:
        return 'first'
    elif chunk_index == total_chunks:
        return 'last'
    else:
        return 'middle'


def chunk_file(input_file_path, output_dir, relative_dir=None, chunking_strategy="by_title", max_characters=1000, overlap=0):
    """
    Chunk a single file using Unstructured open source library.

    Args:
        input_file_path: Path to input file
        output_dir: Base output directory
        relative_dir: Relative directory path to preserve structure (optional)
        chunking_strategy: Chunking strategy to use (basic, by_title)
        max_characters: Maximum characters per chunk
        overlap: Number of characters to overlap between chunks
    """
    start_time = time.time()
    input_path = Path(input_file_path)
    file_name = input_path.stem
    file_ext = input_path.suffix.lower()

    # Display relative path if available for clarity
    display_path = str(Path(relative_dir) / input_path.name) if relative_dir else input_path.name

    print(f"\n{Colors.BOLD}{Colors.BG_BLUE} PROCESSING FILE {Colors.RESET}")
    log_metric("File", display_path)
    log_metric("Type", file_ext.upper())
    log_metric("Strategy", chunking_strategy)
    print()

    # Get file path with up to 2 parents
    file_path_with_parents = get_file_path_with_parents(input_path.resolve(), num_parents=2)

    # Get current date and time
    chunk_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        # Step 1: Partition the document
        log_step("STEP 1/4", "Extracting document elements...", "processing")
        partition_start = time.time()

        if file_ext == ".pdf":
            if partition_pdf is None:
                log_step("ERROR", "PDF support not installed (missing unstructured[pdf])", "error")
                return
            log_detail("Using PDF partitioner with 'auto' strategy")
            elements = partition_pdf(
                filename=str(input_file_path),
                strategy="auto"  # Can be "fast", "hi_res", or "auto"
            )
        elif file_ext == ".md":
            log_detail("Using Markdown partitioner")
            elements = partition_md(filename=str(input_file_path))
        else:
            log_step("ERROR", f"Unsupported file type: {file_ext}", "error")
            return

        partition_time = time.time() - partition_start

        if not elements:
            log_step("WARNING", f"No elements extracted from {input_path.name}", "warning")
            return

        log_step("STEP 1/4", f"Extracted {len(elements)} elements in {format_time(partition_time)}", "success")

        # Step 2: Apply chunking strategy
        log_step("STEP 2/4", f"Applying '{chunking_strategy}' chunking strategy...", "processing")
        log_detail(f"Max characters: {max_characters}, Overlap: {overlap}")
        chunking_start = time.time()

        if chunking_strategy == "by_title":
            chunks = chunk_by_title(
                elements=elements,
                max_characters=max_characters,
                new_after_n_chars=int(max_characters * 0.8),
                combine_text_under_n_chars=100,
                overlap=overlap,
            )
        elif chunking_strategy == "basic":
            chunks = chunk_elements(
                elements=elements,
                max_characters=max_characters,
                new_after_n_chars=int(max_characters * 0.8),
                overlap=overlap,
            )
        else:
            log_step("ERROR", f"Unsupported chunking strategy: {chunking_strategy}", "error")
            log_detail("Available strategies: basic, by_title")
            return

        chunking_time = time.time() - chunking_start

        if not chunks:
            log_step("WARNING", f"No chunks generated for {input_path.name}", "warning")
            return

        log_step("STEP 2/4", f"Generated {len(chunks)} chunks in {format_time(chunking_time)}", "success")

        # Get total chunk count for position calculation
        total_chunks = len(chunks)

        # Step 3: Prepare output directory
        log_step("STEP 3/4", "Preparing output directory...", "processing")

        if relative_dir:
            chunk_output_dir = Path(output_dir) / relative_dir
            chunk_output_dir.mkdir(parents=True, exist_ok=True)
            log_detail(f"Output: {chunk_output_dir}")
        else:
            chunk_output_dir = Path(output_dir)
            log_detail(f"Output: {chunk_output_dir}")

        log_step("STEP 3/4", "Output directory ready", "success")

        # Step 4: Save chunks with metadata
        log_step("STEP 4/4", f"Saving {total_chunks} chunks with enriched metadata...", "processing")
        save_start = time.time()

        for idx, chunk in enumerate(chunks, start=1):
            chunk_filename = f"{file_name}_chunk_{idx}.json"
            chunk_path = chunk_output_dir / chunk_filename

            # Get existing metadata
            existing_metadata = chunk.metadata.to_dict() if hasattr(chunk, 'metadata') else {}

            # Extract coordinates from original elements
            coordinates = extract_coordinates(chunk)

            # Extract detection class probabilities
            detection_probs = extract_detection_class_prob(chunk)

            # Calculate fingerprint for deduplication
            fingerprint = calculate_fingerprint(chunk.text)

            # Determine chunk position
            chunk_position = determine_chunk_position(idx, total_chunks)

            # Add custom metadata fields
            existing_metadata.update({
                "source_file_path": file_path_with_parents,
                "chunking_date": chunk_date,
                "chunking_strategy": chunking_strategy,
                "max_characters": max_characters,
                "chunk_index": idx,
                "total_chunks": total_chunks,
                "chunk_position": chunk_position,
                "fingerprint": fingerprint,
            })

            # Add optional fields only if they have values
            if coordinates:
                existing_metadata["coordinates"] = coordinates

            if detection_probs:
                existing_metadata["detection_class_prob"] = detection_probs

            # Convert element to dictionary
            chunk_data = {
                "text": chunk.text,
                "type": chunk.category if hasattr(chunk, 'category') else str(type(chunk).__name__),
                "metadata": existing_metadata
            }

            # Make all data JSON-serializable to prevent errors with complex objects
            serializable_chunk_data = make_serializable(chunk_data)

            # Save to file
            with open(chunk_path, "w", encoding="utf-8") as f:
                json.dump(serializable_chunk_data, f, indent=2, ensure_ascii=False)

            # Log progress for larger files
            if idx % 10 == 0 or idx == total_chunks:
                log_detail(f"Saved {idx}/{total_chunks} chunks", indent=4)

        save_time = time.time() - save_start
        total_time = time.time() - start_time

        log_step("STEP 4/4", f"Saved all chunks in {format_time(save_time)}", "success")

        # Summary
        print()
        print(f"{Colors.BOLD}{Colors.GREEN}{'─'*80}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.GREEN}✓ COMPLETED SUCCESSFULLY{Colors.RESET}")
        log_metric("Total chunks", total_chunks)
        log_metric("Total time", format_time(total_time))
        log_metric("Avg time/chunk", format_time(total_time / total_chunks))
        print(f"{Colors.BOLD}{Colors.GREEN}{'─'*80}{Colors.RESET}")

    except Exception as e:
        total_time = time.time() - start_time
        print()
        print(f"{Colors.BOLD}{Colors.RED}{'─'*80}{Colors.RESET}")
        log_step("ERROR", f"Failed to process {input_path.name}", "error")
        log_detail(f"Error: {str(e)}", indent=4)
        log_detail(f"Time elapsed: {format_time(total_time)}", indent=4)
        print(f"{Colors.BOLD}{Colors.RED}{'─'*80}{Colors.RESET}")

        import traceback
        print(f"\n{Colors.DIM}Stack trace:{Colors.RESET}")
        traceback.print_exc()
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Chunk PDF and MD files using Unstructured open source library (no API key needed)"
    )
    parser.add_argument(
        "input_dir",
        help="Directory containing input files (PDF and MD)"
    )
    parser.add_argument(
        "output_dir",
        help="Directory to save chunked output files"
    )
    parser.add_argument(
        "--strategy",
        choices=["basic", "by_title"],
        default="by_title",
        help="Chunking strategy (default: by_title)"
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=1000,
        help="Maximum characters per chunk (default: 1000)"
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=0,
        help="Number of characters to overlap between chunks (default: 0)"
    )

    args = parser.parse_args()

    # Print header
    log_header("🚀 Mergen AI DOCUMENT CHUNKER - Powered by Unstructured")

    # Validate directories
    log_step("INIT", "Validating directories...", "processing")
    input_dir = Path(args.input_dir)
    if not input_dir.exists() or not input_dir.is_dir():
        log_step("ERROR", f"Input directory '{input_dir}' does not exist", "error")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_step("INIT", "Directories validated", "success")

    # Find all PDF and MD files recursively
    log_step("SCAN", "Scanning for documents...", "processing")
    supported_extensions = [".pdf", ".md"]
    files_to_process = []

    for ext in supported_extensions:
        # Use rglob for recursive search
        for file_path in input_dir.rglob(f"*{ext}"):
            if file_path.is_file():
                files_to_process.append(file_path)

    if not files_to_process:
        log_step("WARNING", f"No PDF or MD files found in {input_dir}", "warning")
        sys.exit(0)

    log_step("SCAN", f"Found {len(files_to_process)} files to process", "success")

    # Display configuration
    print()
    print(f"{Colors.BOLD}{Colors.CYAN}Configuration:{Colors.RESET}")
    log_metric("Input directory", input_dir)
    log_metric("Output directory", output_dir)
    log_metric("Chunking strategy", args.strategy)
    log_metric("Max characters", args.max_chars)
    log_metric("Overlap", args.overlap)
    log_metric("Total files", len(files_to_process))

    # Process each file
    start_time = time.time()
    success_count = 0
    error_count = 0

    log_header(f"📄 PROCESSING {len(files_to_process)} DOCUMENTS")

    for file_idx, file_path in enumerate(files_to_process, start=1):
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}[{file_idx}/{len(files_to_process)}]{Colors.RESET}")
        try:
            # Calculate relative path from input_dir to preserve directory structure
            relative_path = file_path.parent.relative_to(input_dir)

            # Convert "." (current dir) to None for cleaner handling
            relative_dir = str(relative_path) if str(relative_path) != "." else None

            chunk_file(
                file_path,
                output_dir,
                relative_dir=relative_dir,
                chunking_strategy=args.strategy,
                max_characters=args.max_chars,
                overlap=args.overlap
            )
            success_count += 1
        except Exception:
            error_count += 1

    # Final summary
    total_time = time.time() - start_time

    log_header("📊 PROCESSING SUMMARY")

    if error_count == 0:
        print(f"{Colors.BOLD}{Colors.GREEN}All files processed successfully!{Colors.RESET}\n")
    else:
        print(f"{Colors.BOLD}{Colors.YELLOW}Processing completed with some errors{Colors.RESET}\n")

    log_metric("Total files", len(files_to_process))
    log_metric("Successful", success_count, f" {Colors.GREEN}✓{Colors.RESET}")
    log_metric("Failed", error_count, f" {Colors.RED if error_count > 0 else Colors.DIM}✗{Colors.RESET}")
    log_metric("Total time", format_time(total_time))
    log_metric("Avg time/file", format_time(total_time / len(files_to_process)))
    print()
    log_metric("Output location", output_dir)

    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.GREEN}✨ Chunking journey complete! ✨{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}\n")


if __name__ == "__main__":
    main()
