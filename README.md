<p align="right">
  <strong>English</strong> | <a href="./README_CN.md">简体中文</a>
</p>

# Image Classifier

<div align="center">

![Version](https://img.shields.io/badge/version-7.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)
![License](https://img.shields.io/badge/license-MIT-orange.svg)

A high-performance desktop app for organizing and classifying large image collections.

[Download](#download) • [Features](#features) • [Installation](#installation) • [Usage](#usage) • [Build](#build--release) • [Update](#auto-update)

</div>

## Overview

Image Classifier is a PyQt6-based Windows application designed for fast image triage and folder-based classification. It supports large datasets, custom shortcuts, network path optimization, and persistent workflow state.

## Download

- Latest release page: https://github.com/Gaq152/image_classifier/releases
- Latest manifest: https://github.com/Gaq152/image_classifier/releases/latest/download/manifest.json

| Version | Platform | Asset |
|---|---|---|
| Latest | Windows | `ImageClassifier_vX.Y.Z.exe` |

## Features

- Multi-format support: JPG, JPEG, PNG, BMP, GIF, TIFF, WebP
- High-performance image preload and cache strategy
- Custom category shortcuts (1-9, A-Z)
- Copy / move modes and single / multi-category modes
- Network path optimization for SMB/NAS scenarios
- Persistent classification state and config
- Built-in update check from GitHub Releases manifest

## Installation

### Option 1: Run executable (recommended)

1. Open: https://github.com/Gaq152/image_classifier/releases
2. Download the latest `ImageClassifier_vX.Y.Z.exe`
3. Double-click to run

### Option 2: Run from source

```bash
git clone https://github.com/Gaq152/image_classifier.git
cd image_classifier
pip install -r requirements.txt
python run.py
```

## Usage

1. Launch the app
2. Open an image folder
3. Add categories
4. Classify with buttons or shortcuts

### Default shortcuts

| Shortcut | Action |
|---|---|
| `←` `→` | Previous/next image |
| `↑` `↓` | Navigate categories |
| `Enter` | Classify to selected category |
| `1`-`9`, `A`-`Z` | Quick classify |
| `Delete` | Move to remove folder |
| `F5` | Refresh folder |
| `Ctrl+F` | Fit image to window |
| `Ctrl +/-/0` | Zoom in/out/reset |

## Project Structure

```text
image_classifier/
├── core/                # core logic
├── ui/                  # UI modules and dialogs
├── utils/               # utility modules
├── assets/              # icons and static assets
├── run.py               # app launcher
├── main.py              # entry point
├── build.py             # local build script
└── _version_.py         # single source of version metadata
```

## Build & Release

### GitHub Actions release pipeline

- Workflow file: `.github/workflows/build-release.yml`
- Trigger: `push` tags matching `v*`
- Output assets:
  - `ImageClassifier_vX.Y.Z.exe`
  - `manifest.json`

### Local build

```bash
pip install -r requirements.txt
pip install pyinstaller
python build.py
```

## Auto Update

The app checks updates using:

- Manifest endpoint: `https://github.com/Gaq152/image_classifier/releases/latest/download/manifest.json`
- Download URL: provided by the `url` field in `manifest.json`

`manifest.json` fields used by the app:
- `version`
- `url`
- `sha256`
- `size_bytes`
- `notes`

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

MIT License. See [LICENSE](LICENSE).
