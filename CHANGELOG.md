# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Advanced Analysis workspace: the "Overview" category now shows a
  structural summary of the selected dataset (row/column counts, missing
  values, duplicate rows, and a breakdown of column counts by type), with
  columns above a missing-value threshold flagged as potential issues.

### Changed
- Advanced Analysis workspace: analyses now always run as background jobs
  with a busy overlay shown over the result pane, so large datasets no
  longer freeze the application while an analysis is computed.

### Fixed
- Standard dialog buttons using the "Close" role (Advanced Analysis
  workspace, Column properties) now correctly localize with the
  application's active language instead of always showing English text.
- Advanced Analysis workspace: removed a leftover "Select an analysis from
  the list on the left" message that could never be reached now that an
  analysis category (Overview) is always selected by default.

### Removed
- Removed the legacy "Visualize data" dialog and its chart-configuration
  workflow, in preparation for a new Advanced Analysis workspace.

## [1.0.0] - 2026-09-13

### Added
- Initial release.
