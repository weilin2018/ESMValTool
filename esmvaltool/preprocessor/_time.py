"""Time operations on cubes.

Allows for selecting data subsets using certain time bounds;
constructing seasonal and area averages.
"""
import logging

import iris
import iris.coord_categorisation
import numpy as np

from .._config import use_legacy_iris

logger = logging.getLogger(__name__)


def extract_time(cube, start_year, start_month, start_day, end_year, end_month,
                 end_day):
    """Extract a time range from a cube.

    Parameters
    ----------
        cube: iris.cube.Cube
            input cube.
        start_year: int
            start year
        start_month: int
            start month
        start_day: int
            start day
        end_year: int
            end year
        end_month: int
            end month
        end_day: int
            end day

    Returns
    -------
    iris.cube.Cube
        Sliced cube.

    """
    import datetime
    time_units = cube.coord('time').units
    if time_units.calendar == '360_day':
        if start_day > 30:
            start_day = 30
        if end_day > 30:
            end_day = 30
    start_date = datetime.datetime(
        int(start_year), int(start_month), int(start_day))
    end_date = datetime.datetime(int(end_year), int(end_month), int(end_day))

    t_1 = time_units.date2num(start_date)
    t_2 = time_units.date2num(end_date)
    if use_legacy_iris():
        constraint = iris.Constraint(time=lambda t: (t_1 < t.point < t_2))
    else:
        constraint = iris.Constraint(
            time=lambda t: (t_1 < time_units.date2num(t.point) < t_2))

    cube_slice = cube.extract(constraint)

    # Issue when time dimension was removed when only one point as selected.
    if cube_slice.ndim != cube.ndim:
        time_1 = cube.coord('time')
        time_2 = cube_slice.coord('time')
        if time_1 == time_2:
            logger.debug('No change needed to time.')
            return cube

    return cube_slice


def extract_season(cube, season):
    """
    Slice cube to get only the data belonging to a specific season.

    Parameters
    ----------
    cube: iris.cube.Cube
        Original data
    season: str
        Season to extract. Available: DJF, MAM, JJA, SON
    """
    if not cube.coords('clim_season'):
        iris.coord_categorisation.add_season(cube, 'time', name='clim_season')
    if not cube.coords('season_year'):
        iris.coord_categorisation.add_season_year(
            cube, 'time', name='season_year')
    return cube.extract(iris.Constraint(clim_season=season.lower()))


def extract_month(cube, month):
    """
    Slice cube to get only the data belonging to a specific month.

    Parameters
    ----------
    cube: iris.cube.Cube
        Original data
    month: int
        Month to extract as a number from 1 to 12
    """
    if month not in range(1, 13):
        raise ValueError('Please provide a month number between 1 and 12.')
    return cube.extract(iris.Constraint(month_number=month))


def get_time_weights(cube):
    """
    Compute the weighting of the time axis.

    Parameters
    ----------
        cube: iris.cube.Cube
            input cube.

    Returns
    -------
    numpy.array
        Array of time weights for averaging.
    """
    time = cube.coord('time')
    time_thickness = time.bounds[..., 1] - time.bounds[..., 0]

    # The weights need to match the dimensionality of the cube.
    slices = [None for i in cube.shape]
    coord_dim = cube.coord_dims('time')[0]
    slices[coord_dim] = slice(None)
    time_thickness = np.abs(time_thickness[tuple(slices)])
    ones = np.ones_like(cube.data)
    time_weights = time_thickness * ones
    return time_weights


def time_average(cube):
    """
    Compute time average.

    Get the time average over the entire cube. The average is weighted by the
    bounds of the time coordinate.

    Parameters
    ----------
        cube: iris.cube.Cube
            input cube.

    Returns
    -------
    iris.cube.Cube
        time averaged cube.
    """
    time_weights = get_time_weights(cube)

    return cube.collapsed('time', iris.analysis.MEAN, weights=time_weights)


# get the seasonal mean
def seasonal_mean(cube):
    """
    Function to compute seasonal means with MEAN

    Chunks time in 3-month periods and computes means over them;

    Arguments
    ---------
        cube: iris.cube.Cube
            input cube.

    Returns
    -------
    iris.cube.Cube
        Seasonal mean cube
    """
    if not cube.coords('clim_season'):
        iris.coord_categorisation.add_season(cube, 'time', name='clim_season')
    if not cube.coords('season_year'):
        iris.coord_categorisation.add_season_year(
            cube, 'time', name='season_year')
    cube = cube.aggregated_by(['clim_season', 'season_year'],
                              iris.analysis.MEAN)

    # TODO: This preprocessor is not calendar independent.
    def spans_three_months(time):
        """Check for three months"""
        return (time.bound[1] - time.bound[0]) == 2160

    three_months_bound = iris.Constraint(time=spans_three_months)
    return cube.extract(three_months_bound)


def annual_mean(cube, decadal=False):
    """
    Compute annual or decadal means.

    Note that this function does not weight the annual or decadal mean if
    uneven time periods are present. Ie, all data inside the year/decade
    are treated equally.

    Parameters
    ----------
        cube: iris.cube.Cube
            input cube.
        decadal: bool
            Annual average (:obj:`True`) or decadal average (:obj:`False`)
    Returns
    -------
    iris.cube.Cube
        Annual mean cube
    """
    def get_decade(coord, value):
        """Callback function to get decades from cube."""
        date = coord.units.num2date(value)
        return date.year - date.year % 10

    # time_weights = get_time_weights(cube)

    # TODO: Add weighting in time dimension. See iris issue 3290
    # https://github.com/SciTools/iris/issues/3290

    if decadal:
        iris.coord_categorisation.add_categorised_coord(cube, 'decade',
                                                        'time', get_decade)
        return cube.aggregated_by('decade', iris.analysis.MEAN)

    return cube.aggregated_by('year', iris.analysis.MEAN)
