# --- Dataframe sanitization and truncation ---
from typing import Any, Optional
import numpy as np
import pandas as pd


def value_str_or_empty_str(v: Any) -> str:
    """
    Convert v to str, or empty string for null-like values.

    str(np.nan) is 'nan', and we don't want that. This function returns ''
    instead.
    """
    if isinstance(v, str):
        return v  # common case
    if v is np.nan or v is pd.NaT or v is None:
        return ''
    else:
        return str(v)


def safe_column_to_string(col: pd.Series) -> pd.Series:
    """Convert numbers to str, replacing NaN with ''."""
    return col.apply(value_str_or_empty_str)


def _colname_to_str(c: Any) -> str:
    """
    Cast a column name to str.

    In the case of a float column name, this method optimizes for the fewest
    zeros possible.
    """
    if isinstance(c, float):
        return '%g' % c
    else:
        return str(c)


def _rename_duplicate_columns_in_place(table: pd.DataFrame) -> None:
    """
    Modify column names so they are all unique.
    """
    newcols = []
    for item in table.columns:
        counter = 0
        newitem = _colname_to_str(item)
        while newitem in newcols:
            counter += 1
            newitem = newitem + '_' + str(counter)
        newcols.append(newitem)
    table.columns = newcols


# full type list:
# https://pandas.pydata.org/pandas-docs/stable/generated/pandas.api.types.infer_dtype.html
_AllowedDtypes = {
    'boolean',
    # categorical is a special case
    'date',
    'datetime',
    'floating',
    'integer',
    'string',
    'time',
}


def sanitize_series(series: pd.Series) -> pd.Series:
    """
    Build a Series conforming to Workbench data types.

    The return value is a valid argument to `hash_pandas_object()` and can be
    written to a parquet file.

    Specific fixes:

    * Convert unsupported dtypes to string.
    """
    dtype = pd.api.types.infer_dtype(series)
    if dtype == 'categorical':
        col_dtype = pd.api.types.infer_dtype(series.cat.categories)
        if col_dtype not in _AllowedDtypes:
            # Convert categories to str
            return series.cat.rename_categories(
                series.cat.categories.apply(value_str_or_empty_str)
            )
        else:
            return series
    elif dtype not in _AllowedDtypes:
        return series.apply(value_str_or_empty_str)
    else:
        return series


def sanitize_dataframe(table: Optional[pd.DataFrame]) -> pd.DataFrame:
    """
    Modify table in-place to conform to Workbench data types.

    After calling this method on a table, `hash_pandas_object()` will work and
    writing to parquet format will be viable.

    Specific fixes:

    * Convert `None` to an empty DataFrame.
    * Modify duplicate column names.
    * Reindex so row numbers are contiguous.
    * Convert unsupported dtypes to string.
    """
    if table is None:
        return pd.DataFrame()

    for colname in table.columns:
        column = table[colname]
        sane_column = sanitize_series(column)
        if sane_column is not column:  # avoid SettingWithCopyWarning
            table[colname] = sane_column

    _rename_duplicate_columns_in_place(table)

    # renumber row indices so always 0..n
    table.index = pd.RangeIndex(len(table.index))

    return table


def autocast_series_dtype(series: pd.Series) -> pd.Series:
    """
    Cast str/object series to numeric, if possible.

    This is appropriate when parsing CSV data, or maybe Excel data. It _seems_
    appropriate when a search-and-replace produces numeric columns like
    '$1.32' => '1.32' ... but perhaps that's only appropriate in very-specific
    cases.

    TODO handle dates and maybe booleans.
    """
    if series.dtype == 'O':
        # Object (str) series. Try to infer type.
        #
        # We don't case from complex to simple types here: we assume the input
        # is already sane.
        try:
            return pd.to_numeric(series)
        except ValueError:
            return series
    elif hasattr(series, 'cat'):
        # Categorical series. Try to infer type of series.
        try:
            # Replace empty str with nan -- will help to_numeric
            if '' in series.cat.categories:
                series = series.cat.remove_categories([''])
            categories = pd.to_numeric(series.cat.categories)
            series.cat.rename_categories(categories, inplace=True)
            # Expand categories. This will likely save space for int8 and cost
            # space for float64. [2018-07-3] The only strong rationale at the
            # moment (either for or against this approach) is simplifying unit
            # tests.
            return series.astype(series.cat.categories.dtype)
        except ValueError as err:
            return series


def autocast_dtypes_in_place(table: pd.DataFrame) -> None:
    """
    Cast str/object columns to numeric, if possible.

    This is appropriate when parsing CSV data, or maybe Excel data. It is
    probably not appropriate to call this method elsewhere, since it destroys
    data types all over the table.

    TODO handle dates and maybe booleans.
    """
    for colname in table:
        column = table[colname]
        table[colname] = autocast_series_dtype(column)


def truncate_table_if_too_big(df):
    """
    Limit table size to max allowed number of rows.

    Return whether we modified the table.
    """
    # Import here, so that the pythoncode module does not need to import django
    from django.conf import settings

    nrows = len(df)
    if nrows > settings.MAX_ROWS_PER_TABLE:
        df.drop(range(settings.MAX_ROWS_PER_TABLE, nrows), inplace=True)
        return True
    else:
        return False
