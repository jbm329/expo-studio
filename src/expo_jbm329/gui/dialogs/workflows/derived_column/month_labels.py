"""Capture standalone month translations before dispatching Derived work."""

from PyQt6.QtCore import QT_TRANSLATE_NOOP

from expo_jbm329.services.data_operations.derived_column.derived_column_time import MonthLabels
from expo_jbm329.utils.i18n_utils import translate

_FULL_MONTHS = (
    QT_TRANSLATE_NOOP("DerivedColumnMonths", "January"),
    QT_TRANSLATE_NOOP("DerivedColumnMonths", "February"),
    QT_TRANSLATE_NOOP("DerivedColumnMonths", "March"),
    QT_TRANSLATE_NOOP("DerivedColumnMonths", "April"),
    QT_TRANSLATE_NOOP("DerivedColumnMonths", "May"),
    QT_TRANSLATE_NOOP("DerivedColumnMonths", "June"),
    QT_TRANSLATE_NOOP("DerivedColumnMonths", "July"),
    QT_TRANSLATE_NOOP("DerivedColumnMonths", "August"),
    QT_TRANSLATE_NOOP("DerivedColumnMonths", "September"),
    QT_TRANSLATE_NOOP("DerivedColumnMonths", "October"),
    QT_TRANSLATE_NOOP("DerivedColumnMonths", "November"),
    QT_TRANSLATE_NOOP("DerivedColumnMonths", "December"),
)
_SHORT_MONTHS = (
    QT_TRANSLATE_NOOP("DerivedColumnShortMonths", "Jan"),
    QT_TRANSLATE_NOOP("DerivedColumnShortMonths", "Feb"),
    QT_TRANSLATE_NOOP("DerivedColumnShortMonths", "Mar"),
    QT_TRANSLATE_NOOP("DerivedColumnShortMonths", "Apr"),
    QT_TRANSLATE_NOOP("DerivedColumnShortMonths", "May"),
    QT_TRANSLATE_NOOP("DerivedColumnShortMonths", "Jun"),
    QT_TRANSLATE_NOOP("DerivedColumnShortMonths", "Jul"),
    QT_TRANSLATE_NOOP("DerivedColumnShortMonths", "Aug"),
    QT_TRANSLATE_NOOP("DerivedColumnShortMonths", "Sep"),
    QT_TRANSLATE_NOOP("DerivedColumnShortMonths", "Oct"),
    QT_TRANSLATE_NOOP("DerivedColumnShortMonths", "Nov"),
    QT_TRANSLATE_NOOP("DerivedColumnShortMonths", "Dec"),
)


def capture_month_labels() -> MonthLabels:
    """Snapshot app-language labels on the GUI thread when accepting a formula.

    Full and abbreviated names use separate translation contexts because the
    English word May is shared but its translated abbreviation may differ.

    Returns:
        Immutable labels suitable for both service preview and worker execution.
    """
    return MonthLabels(
        full=tuple(translate("DerivedColumnMonths", month) for month in _FULL_MONTHS),
        short=tuple(translate("DerivedColumnShortMonths", month) for month in _SHORT_MONTHS),
    )
