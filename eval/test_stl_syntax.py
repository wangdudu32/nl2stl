import csv

from stl_syntax_validator import stl_syntax_validator


csv_file = "deepstl_test_2k.csv"

total_count = 0
pass_count = 0
fail_count = 0

with open(csv_file, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    for row_index, row in enumerate(reader, start=2):
        stl = row["STL"]
        total_count += 1

        if stl_syntax_validator(stl):
            pass_count += 1
        else:
            fail_count += 1
            print(f"Failed at CSV row {row_index}: {stl}")

print(f"Total: {total_count}")
print(f"Passed: {pass_count}")
print(f"Failed: {fail_count}")
