# Automacao-Ordens-de-Servico | Vehicle Service Order Automation

A robust Python automation pipeline that monitors designated directories, extracts vehicle license plates via OCR, converts image documents to standardized PDFs, and systematically archives records by registration number. Designed to streamline service order management, eliminate manual filing, and ensure consistent, audit-ready documentation.

## ✨ Key Features
- **Real-time Filesystem Monitoring**: Event-driven directory watcher with configurable triggers and debounce logic
- **OCR-Powered Plate Recognition**: High-accuracy text extraction using Tesseract + OpenCV preprocessing (noise reduction, thresholding, perspective correction)
- **Automated PDF Generation**: Converts images to standardized, metadata-rich PDF documents
- **Dynamic Directory Organization**: Automatically creates and structures folders by vehicle plate with format validation
- **Secure Asset Archival**: Moves processed images to a dedicated `processed/` directory with full traceability
- **Production-Ready Observability**: Structured logging, error isolation, and configurable retry mechanisms

## 🔄 Workflow
1. **Ingestion**: Image placed in monitored `input/` directory
2. **Event Detection**: Watchdog triggers pipeline on file creation/modification
3. **Preprocessing & OCR**: OpenCV enhances image quality; Tesseract extracts license plate text
4. **Validation & Routing**: Validates plate format against regional regex; creates target directory if absent
5. **PDF Conversion & Storage**: Generates standardized PDF and archives it in the vehicle-specific folder
6. **Cleanup & Logging**: Moves original to `processed/`, logs success/failure with timestamps and diagnostic codes

## 🛠️ Technology Stack
| Component       | Library/Tool          | Purpose                              |
|-----------------|-----------------------|--------------------------------------|
| Core Language   | Python 3.10+          | Pipeline orchestration               |
| File Monitoring | Watchdog              | Real-time filesystem event handling  |
| Image Processing| OpenCV                | Preprocessing, enhancement, validation |
| OCR Engine      | Tesseract OCR + `pytesseract` | License plate text extraction    |
| Image/PDF Handling | Pillow, `img2pdf`   | Conversion, formatting, metadata     |
| Configuration & Logging | `logging`, `pyyaml` | Structured logging & config management |
