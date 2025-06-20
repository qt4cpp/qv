# qv

qv is a simple Qt-based DICOM volume renderer using VTK.

It allows loading a directory of DICOM files and visualizing them with volume rendering.

## Usage

```bash
python -m qv /path/to/dicom/series
```

or just run `python -m qv` to open a dialog for selecting the DICOM directory.

## Requirements

- Python 3.9+
- Qt for Python (PySide6)
- VTK

