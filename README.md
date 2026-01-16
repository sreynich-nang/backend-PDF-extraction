# 📘 Marker Backend — Project Documentation

## 1. Overview

**Marker Backend** is a FastAPI-based service designed to extract structured and unstructured content from **PDFs and images** using the `marker` tool. It converts documents into **Markdown format**, enabling downstream processing such as table extraction, data analysis, or document indexing.

The system is optimized for **GPU acceleration** but supports CPU execution when GPUs are unavailable.

---

## 2. System Goals

* Accept PDFs and images through an API
* Run the `marker` extraction pipeline
* Produce structured Markdown outputs
* Allow users to download extracted results
* Optionally extract tables into CSV for analytics workflows

---

## 3. High-Level Architecture

```
Client (Browser / Frontend / API Tool)
            │
            ▼
     FastAPI Backend
            │
            ▼
    Marker Processing Engine
            │
            ▼
   Markdown + CSV Outputs
```

---

## 4. Project Structure (Markdown Diagram)

```
MarkerV4/
├── environment.yml
├── marker_backend/
│   ├── main.py
│   ├── api/
│   │   └── endpoints.py
│   ├── core/
│   │   ├── config.py
│   │   ├── exceptions.py
│   │   └── logger.py
│   ├── models/
│   ├── services/
│   │   ├── file_handler.py
│   │   ├── gpu_manager.py
│   │   ├── marker_runner.py
│   │   ├── pdf_converter.py
│   │   └── table_extractor.py
│   └── utils/
└── temp/
    ├── uploads/
    ├── filters/
    ├── pdf2image/
    └── outputs/
```

---

## 5. Component-by-Component Breakdown

### 5.1 Entry Point — `marker_backend/main.py`

**Purpose:**
Bootstraps the FastAPI application and exposes HTTP endpoints.

**Responsibilities:**

* Creates the FastAPI app instance
* Registers middleware (CORS), which allow for all
* Includes API routers
* Launches the application using Uvicorn

**Execution Flow:**

```
Start app → Load config → Register routes → Enable CORS → Serve requests
```

---

### 5.2 API Layer — `marker_backend/api/endpoints.py`

This layer defines all external HTTP endpoints.

#### 🔹 `POST /api/upload`

**Purpose:**
Accepts a document file (PDF or image) and processes it using `marker`.

**Workflow:**

1. Accept multipart file upload
2. Save file to `temp/uploads/`
3. Detect file type:
   * **PDF** → run PDF conversion + marker pipeline
   * **Image** → directly run marker
4. Measure processing time
5. Return processing metadata of the combination after marker processing

**Response Example:**

```json
{
  "status": "success",
  "filename": "document.md",
  "processing_time": 8.24
}
```

---

#### 🔹 `GET /api/download/{filename}`

**Purpose:**
Allows users to download the generated Markdown output.

**Workflow:**

1. Resolve file path in `temp/outputs/`
2. Validate file existence
3. Return file as a downloadable response

---

### 5.3 Core Layer

#### 📁 `marker_backend/core/config.py`

**Purpose:**
Central configuration source.

**Manages:**

* Directory paths (`uploads/`, `filters/`, `pdf2image/`, `outputs/`)
* Host and port
* Marker binary paths
* Environment flags

---

#### 📁 `marker_backend/core/logger.py`

**Purpose:**
Defines structured logging behavior across the application.

**Capabilities:**

* Console logging
* Standardized log formatting
* Module-level logger injection

---

#### 📁 `marker_backend/core/exceptions.py`

**Purpose:**
Custom application-level exceptions for:

* File validation
* Marker execution failures
* GPU availability errors

---

### 5.4 Services Layer (Business Logic)

This layer performs all processing work which include all about the Marker tasking, not the cleaning and transforming to Tidy, yet (Future Work)

---

#### 📁 `services/file_handler.py`

**Purpose:**
Handles filesystem operations for uploaded and generated files.

**Responsibilities:**

* Save uploaded files safely
* Generate unique filenames
* Validate file types
* Clean up temporary files if needed

---

#### 📁 `services/gpu_manager.py`

**Purpose:**
Detects GPU availability and readiness before running marker.

**Responsibilities:**

* Check CUDA device availability
* Validate memory capacity
* Fall back to CPU execution if necessary

---

#### 📁 `services/marker_runner.py`

**Purpose:**
Acts as a wrapper around the `marker` CLI tool.

**Responsibilities:**

* Construct command-line arguments
* Invoke `marker` via subprocess
* Capture stdout/stderr
* Handle failures and retries
* Log execution metadata

**Execution Flow:**

```
Input file → Build marker command → Run subprocess → Capture output → Save Markdown → Return path
```

---

#### 📁 `services/pdf_converter.py`

**Purpose:**
Prepares PDF files for processing by splitting or rasterizing them into image chunks (if required by marker).

**Responsibilities:**

* Convert PDF pages into images
* Chunk large PDFs into manageable batches
* Feed chunks into marker_runner
* Merge chunk outputs into a final Markdown document

---

#### 📁 `services/table_extractor.py`

**Purpose:**
Extracts structured tables from Markdown output and converts them into Pandas DataFrames or CSV files (one CSV = one Table).

**Responsibilities:**

* Parse Markdown tables using regex or tokenization
* Normalize headers and rows
* Handle merged cells and malformed tables
* Export tables as CSV for analytics pipelines

**Typical Use Case:**

```
Markdown output → Table detection → DataFrame → CSV export
```

---

## 6. End-to-End Workflow

### 6.1 Upload & Processing Flow

```
User Upload
   │
   ▼
POST /api/upload => Save to temp/uploads/
   │
   ▼
File Type Detection
   │
   ├── PDF → pdf_converter → marker_runner
   └── Image → marker_runner
   │
   ▼
Markdown Output Generated => Save to temp/outputs/
   │
   ▼
Response Returned to Client
```

---

### 6.2 Download Flow

```
User requests /api/download/{filename}
   │
   ▼
Backend resolves temp/outputs/{filename}
   │
   ▼
File streamed to client
```

---

## 7. Directory Responsibilities

| Directory                  | Purpose                                                |
| -------------------------- | -------------------------------------------------------|
| `marker_backend/api/`      | HTTP route definitions                                 |
| `marker_backend/core/`     | Configuration, logging, and exceptions                 |
| `marker_backend/services/` | Business logic and processing pipelines                |
| `marker_backend/models/`   | Data models (schemas, DTOs)                            |
| `marker_backend/utils/`    | Helper utilities                                       |
| `temp/uploads/`            | Temporary storage for incoming files                   |
| `temp/pdf2image/`          | Temporary storage for converting each page to image    |
| `temp/filters/`            | Storage only tables from markdown to each CSV          |
| `temp/outputs/`            | Generated Markdown and CSV results                     |

---

## 8. Runtime Execution Guide

### 8.1 In this PRoject

* Conda or Miniconda
* Python ≥ 3.10
* NVIDIA GeForce RTX 5090
* CUDA Version: 13.0

---

### 8.2 Environment Setup

```bash
conda env create -f environment.yml
conda activate TorchMarker
```

---

### 8.3 Start the Server

From the project root:

```bash
python -m marker_backend.main
```

or using Uvicorn directly:

```bash
uvicorn marker_backend.main:app --host 0.0.0.0 --port 8000 --reload
```

---

### 8.4 Verification

| Endpoint                       | Purpose                          |
| ------------------------------ | -------------------------------- |
| `GET /health`                  | Health check (`{"status":"ok"}`) |
| `GET /docs`                    | Swagger API documentation        |

---

## 9. Error Handling Strategy

* **Validation Errors:**
  Returned as structured HTTP 400 responses.
* **Marker Failures:**
  Captured from subprocess stderr and returned as HTTP 500 with logs.
* **GPU Unavailability:**
  Logged and gracefully downgraded to CPU mode.

---

## 10. Performance Characteristics

| Area        | Behavior                               |
| ----------- | -------------------------------------- |
| PDFs        | Chunked to reduce memory pressure      |
| Images      | Single-pass marker execution           |
| GPU         | Preferred execution path               |
| CPU         | Fallback when GPU unavailable          |

---

## 11. Summary

The **Marker Backend** provides a clean, modular, and production-ready pipeline for:

* Document ingestion
* OCR + layout extraction
* Markdown generation
* Table structuring into CSV
* File download via REST APIs

Its layered architecture (API → Services → Core → Tools) ensures:

* High maintainability
* Clear separation of concerns
* Easy extensibility (e.g., adding new extractors or formats)

# Reference
- [datalab-to/marker](https://github.com/datalab-to/marker)
- [FastAPI](https://fastapi.tiangolo.com/)
