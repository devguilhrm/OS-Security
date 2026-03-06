# Automacao-Ordens-de-Servi-o
Python automation system that monitors a folder, detects vehicle license plates using OCR, converts images to PDF, and automatically organizes files by vehicle plate.

Features:

- Real-time folder monitoring
- License plate detection using OCR
- Automatic PDF generation from images
- Automatic organization of files by vehicle plate
- Separation of processed images

Workflow:
1. A new vehicle image is placed in the input folder.
2. The system detects the file automatically.
3. OCR reads the license plate from the image.
4. A folder is created for the vehicle (if it does not exist).
5. The image is converted into a PDF and stored in the vehicle folder.
6. The original image is moved to a processed folder.

Technologies used:
- Python
- OpenCV
- Tesseract OCR
- Watchdog
- Pillow (PIL)

This project demonstrates automation, file system monitoring, image processing, and basic computer vision techniques for organizing vehicle service records.
