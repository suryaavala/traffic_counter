### Assumptions

1. data is given in a `csv` file with two `unnamed` columns representing `timestamp` and `count`, respectively, separated by whitespace as delimiter and the file is clean
   * data is sorted by `timestamp`, but not contiguous
   * `timestamp` is in `YYYY-MM-DDTHH:MM:SS` ISO 8601 format
   * `count` is an integer

2. not using `pandas` or `polars` (by extension `numpy`, etc..). only trying to do it with standard library

3. avoid over-engineering but professional standards
- made assumptions around data being clean & sorted
- design is simple but modular
- optimising for both time complexity and space complexity
- writing test cases (with edge cases, etc..), lint, minimal pyproject.toml

### Output

- Making outputs more human readable by adding explanatory rows of strings but keeping the data in the same format
- empty file will still print the explanatory strings but with empty data

1. `total_vehicles`: total number of vehicles
2. `daily`: list of tuples with `date` string in ISO 8601 format and `total_vehicles` pairs
3. `top_3_half_hours`: list of `(datetime, count)` tuples representing the top 3 half hours with the highest vehicle counts
   * not necessarily consecutive
   * sorted by count in descending order
   * if there are ties, the earlier half hour is preferred (assuming the input data is already sorted by timestamp in chronological order)
   * if less than 3 half hours are present, return all
4. `least_hour_and_half`: list of `(datetime, count)` tuples representing the least hour and half with the lowest vehicle counts
   * contiguous half hours
   * if there are ties, the earlier half hour is preferred
   * if less than 3 half hours are present, return `None`


### choices

- making the choice of processing row by row instead of heapify, etc.. on the whole data.
- hand crafted:
  - solution except for autocomplete here and there
- use of AI:
  - analysis/review of the solution
  - write docs (docstrings, README)
  - setup tests
  - bootstrap repo


### Dev

- requires `uv` to be installed
`make setup` to install dependencies
`make lint` to lint the code
`make typecheck` to typecheck the code
`make test` to test the code
