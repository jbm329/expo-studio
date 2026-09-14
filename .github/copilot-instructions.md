# Expo Studio - GitHub Copilot Instructions

## Project Overview

Expo Studio is a desktop data analysis application built with PyQt6.

The application supports:

- Interactive SQL development
- Dataset inspection and profiling
- Data cleaning and transformation
- Visualization and charting
- Asynchronous data processing
- Result tab management
- Multiple file formats including CSV, Excel, Parquet, Feather, Pickle, QVD, SPSS and Stata

The codebase prioritizes maintainability, readability, robustness and clean architecture over short-term implementation speed.

When suggesting code, always prefer consistency with the existing architecture.

---

# General Development Principles

## Readability First

Code is read far more often than it is written.

Prefer:

- explicit code
- descriptive names
- small focused methods
- clear control flow

Avoid:

- clever tricks
- hidden side effects
- unnecessary abstractions
- overly compact implementations

---

## DRY

Avoid code duplication.

Before introducing a new implementation:

- look for existing services
- look for reusable helpers
- look for existing utilities

However:

- do not force abstractions too early
- duplicated business rules should never exist

---

## SOLID

Follow SOLID principles when appropriate.

Especially:

- Single Responsibility Principle
- Dependency Inversion Principle

Avoid large classes with mixed responsibilities.

---

## Incremental Change

Do not suggest large rewrites unless explicitly requested.

Prefer:

1. Small focused refactors
2. Backward compatible improvements
3. Gradual architectural improvements

When reviewing existing code:

- preserve working behavior
- minimize risk
- avoid introducing architectural churn

---

# Python Standards

## Language Version

Target modern Python.

Prefer:

- dataclasses when appropriate
- pathlib over os.path
- typing annotations everywhere
- StrEnum when applicable
- match statements when they improve readability

---

## Type Hints

All new code should include type hints.

Example:

```python
def load_dataset(path: Path) -> pd.DataFrame:
    ...
```

Avoid untyped public APIs.

---

## None Safety

Always handle possible None values explicitly.

Prefer:

```python
if value is None:
    return
```

over:

```python
if not value:
    return
```

when None is the actual concern.

Never assume an object exists without verification.

---

## Exceptions

Fail explicitly.

Prefer:

```python
raise ValueError(...)
```

over silent failures.

Avoid:

- bare except
- swallowed exceptions
- generic Exception catches unless justified

If an exception is intentionally handled:

- explain why in comments when not obvious

---

## Logging

Internal logs are always written in English.

Examples:

```python
logger.info("Dataset loaded successfully")
logger.error("Failed to parse SQL statement")
```

Never mix Swedish and English in logs.

---

# Documentation

## Docstrings

Use Google-style docstrings.

Example:

```python
def load_dataset(path: Path) -> pd.DataFrame:
    """Load a dataset from disk.

    Args:
        path: Path to the dataset.

    Returns:
        Loaded dataframe.

    Raises:
        FileNotFoundError:
            If the file does not exist.
    """
```

Docstrings must be written in English.

---

## Comments

Comments must be written in English.

Only explain:

- why
- business rules
- non-obvious decisions

Do not repeat what code already communicates.

Bad:

```python
# Increment counter
counter += 1
```

Good:

```python
# SQL line numbers shown to users are 1-based.
line_number += 1
```

---

# PyQt6 Standards

## Framework

Always use PyQt6.

Never suggest PyQt5 code.

Imports must use PyQt6 namespaces.

---

## Separation of Concerns

UI classes should remain thin.

Avoid:

- business logic in dialogs
- data processing in widgets
- file processing in views

Prefer:

- dialogs
- controllers
- services
- repositories

with clear responsibilities.

---

## Signals and Slots

Use signals and slots for communication.

Avoid tightly coupled widgets communicating directly.

---

## Long Running Operations

Never block the GUI thread.

Long-running work must use:

- worker patterns
- asynchronous jobs
- task managers

UI responsiveness is a priority.

---

# Dependency Injection

Dependency injection is preferred.

Avoid:

```python
service = MyService()
```

inside business logic.

Prefer constructor injection.

Example:

```python
class DatasetController:
    def __init__(
        self,
        dataset_service: DatasetService,
    ) -> None:
        self._dataset_service = dataset_service
```

Dependencies should be explicit and testable.

---

# Architecture Guidelines

## Preferred Layers

When possible follow:

- View
- Controller
- Service
- Repository

Responsibilities should remain separated.

---

## Controllers

Controllers orchestrate behavior.

Controllers should not contain:

- heavy business logic
- SQL parsing
- file parsing

Those responsibilities belong in services.

---

## Services

Services contain business logic.

Services should:

- be testable
- avoid UI dependencies
- minimize side effects

---

## Dialogs and Widgets

Dialogs and widgets should:

- gather input
- present information
- dispatch actions

Avoid implementing business rules directly in UI code.

---

# Pandas Standards

## Data Types

Preserve data types intentionally.

Do not automatically change dtypes without good reason.

When new textual columns are created through:

- split
- cleaning
- joins
- transformations

prefer:

```python
pd.StringDtype()
```

unless another dtype is explicitly required.

---

## Performance

Avoid unnecessary DataFrame copies.

However:

- correctness is more important than micro-optimizations
- readability is more important than premature optimization

---

# SQL Features

Expo Studio contains advanced SQL functionality.

When suggesting SQL-related code:

- prefer sqlglot-compatible approaches
- keep parsing logic separate from UI
- avoid embedding parser logic in widgets
- maintain testability

---

# Result Tabs

Result tab management is a core part of the application.

When working with result tabs:

- preserve existing lifecycle behavior
- avoid tight coupling
- keep responsibilities separated
- prefer explicit ownership

Do not suggest architectural rewrites unless specifically requested.

---

# Async Jobs

Async job execution is a core architectural feature.

Long-running operations should:

- report progress when possible
- support cancellation when appropriate
- propagate correlation identifiers when available
- avoid blocking the UI thread

Cancellation support should only be introduced when it provides real user value.

---

# Testing

New business logic should be testable.

Focus tests on:

- services
- parsers
- utility modules
- business rules

Avoid testing UI implementation details unless necessary.

Prefer deterministic tests.

Avoid timing-sensitive tests.

---

# Code Reviews

When reviewing code:

- prioritize correctness
- prioritize maintainability
- identify architectural issues
- identify None safety issues
- identify typing issues
- identify error handling issues

Do not recommend stylistic changes unless they improve readability or maintainability.

---

# Response Style

When generating code:

- provide production-quality implementations
- include type hints
- include Google-style docstrings
- include robust error handling
- preserve existing architecture

 