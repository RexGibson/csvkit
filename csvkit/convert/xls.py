#!/usr/bin/env python

import csv
from cStringIO import StringIO
import datetime

import xlrd

from csvkit import typeinference
import utils

class XLSDataError(Exception):
    """
    Exception raised when there is a problem converting XLS data.
    """
    def __init__(self, msg):
        self.msg = msg

def normalize_empty(values):
    """
    Normalize a column which contains only empty cells.
    """
    return [None] * len(values)

def normalize_text(values):
    """
    Normalize a column of text cells.
    """
    return [v if v else None for v in values]

def normalize_numbers(values):
    """
    Normalize a column of numeric cells.
    """
    # Test if all values are whole numbers, if so coerce floats it ints
    integral = True

    for v in values:
        if v and v % 1 != 0:
            integral = False
            break

    if integral:
        return [int(v) if v != '' else None for v in values]
    else:
        # Convert blanks to None
        return [v if v else None for v in values]

def normalize_dates(values, datemode):
    """
    Normalize a column of date cells.
    """
    normal_values = []
    normal_types_set = set()

    for v in values:
        # Convert blanks to None
        if v == '':
            normal_values.append(None)
            continue

        v_tuple = xlrd.xldate_as_tuple(v, datemode)

        if v_tuple == (0, 0, 0, 0, 0, 0):
            # Midnight 
            normal_values.append(datetime.time(*v_tuple[3:]))
            normal_types_set.add('time')
        elif v_tuple[3:] == (0, 0, 0):
            # Date only
            normal_values.append(datetime.date(*v_tuple[:3]))
            normal_types_set.add('date')
        elif v_tuple[:3] == (0, 0, 0):
            # Time only
            normal_values.append(datetime.time(*v_tuple[3:]))
            normal_types_set.add('time')
        else:
            # Date and time
            normal_values.append(datetime.datetime(*v_tuple))
            normal_types_set.add('datetime')

    if len(normal_types_set) == 1:
        # No special handling if column contains only one type
        pass 
    elif normal_types_set == set(['datetime', 'date']):
        # If a mix of dates and datetimes, up-convert dates to datetimes
        for i, v in enumerate(normal_values):
            if v.__class__ == datetime.date:
                normal_values[i] = datetime.datetime.combine(v, datetime.time())
    elif normal_types_set == set(['datetime', 'time']):
        # Datetimes and times don't mix
        raise XLSDataError('Column contains a mix of times and datetimes (this is not supported).')
    elif normal_types_set == set(['date', 'time']):
        # Dates and times don't mix
        raise XLSDataError('Column contains a mix of dates and times (this is not supported).')

    # Natural serialization of dates and times by csv.writer is insufficent so they get converted back to strings at this point
    return [v.isoformat() if v != None else None for v in normal_values] 

def normalize_booleans(values):
    """
    Normalize a column of boolean cells.
    """
    return [bool(v) if v != '' else None for v in values] 

NORMALIZERS = {
    xlrd.biffh.XL_CELL_EMPTY: normalize_empty,
    xlrd.biffh.XL_CELL_TEXT: normalize_text,
    xlrd.biffh.XL_CELL_NUMBER: normalize_numbers,
    xlrd.biffh.XL_CELL_DATE: normalize_dates,
    xlrd.biffh.XL_CELL_BOOLEAN: normalize_booleans
}

def determine_column_type(types):
    """
    Determine the correct type for a column from a list of cell types.
    """
    types_set = set(types)
    types_set.discard(xlrd.biffh.XL_CELL_EMPTY)

    if len(types_set) > 1:
        raise XLSDataError('Column contains multiple data types: %s' % str(types_set)) 

    try:
        return types_set.pop()
    except KeyError:
        return xlrd.biffh.XL_CELL_EMPTY

def xls2csv(f):
    """
    Convert an Excel .xls file to csv.
    """
    book = xlrd.open_workbook(file_contents=f.read())
    sheet = book.sheet_by_index(0)

    data_columns = []

    for i in range(sheet.ncols):
        # Trim headers
        column_name = sheet.col_values(i)[0]
        values = sheet.col_values(i)[1:]
        types = sheet.col_types(i)[1:]

        try:
            column_type = determine_column_type(types)

            # This is terrible code. TKTK
            if column_type == xlrd.biffh.XL_CELL_DATE:
                normal_values = NORMALIZERS[column_type](values, book.datemode)
            else:
                normal_values = NORMALIZERS[column_type](values)
        except XLSDataError, e:
            e.msg = 'Error in column %i, "%s": %s' % (i, column_name, e.msg)
            raise e

        data_columns.append(normal_values)

    # Convert columns to rows
    data = zip(*data_columns)

    # Insert header row
    data.insert(0, [sheet.col_values(i)[0] for i in range(sheet.ncols)])

    return utils.rows_to_csv_string(data) 
