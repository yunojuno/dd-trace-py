import csv
import json
import os
import shutil
import statistics
import subprocess
import sys
import typing


def print_spaced(elements):
    # (typing.List[typing.Any]) -> None
    format_str = "{:>12}" * len(elements)
    print(format_str.format(*elements))


def run_sirun(meta_file, variant=None):
    # (str, typing.Optional[str]) -> typing.Dict[str, typing.Any]
    env = os.environ.copy()
    if variant:
        env["SIRUN_VARIANT"] = variant

    sirun_path = shutil.which("sirun")
    args = [sirun_path, meta_file]
    res = subprocess.run(args=args, env=env, capture_output=True)

    if res.returncode != 0:
        print(res.stderr)
        sys.exit(1)

    lines = res.stdout.splitlines()
    return json.loads(lines[-1])


def main(meta_file):
    # (str) -> None
    with open(meta_file) as fp:
        meta = json.load(fp)

    if "variants" in meta:
        variants = meta["variants"].keys()
    else:
        variants = [None]

    for variant in variants:
        print("Variant:", variant)
        result = run_sirun(meta_file, variant=variant)

        if "instructions" in result:
            print("Instructions:", result["instructions"])

        print_spaced(("metric", "iterations", "min", "max", "mean", "p50", "p75", "p90", "p95", "p99"))

        for metric in ("system.time", "user.time", "wall.time", "max.res.size"):
            values = [iteration[metric] for iteration in result["iterations"]]
            per = statistics.quantiles(values, n=100)

            row = [
                metric,
                len(values),
                min(values),
                max(values),
                statistics.mean(values),
            ]
            for p in (50, 75, 90, 95, 99):
                row.append(per[p - 1])

            print_spaced(row)
        print("")


if __name__ == "__main__":
    assert len(sys.argv) == 2, "{} <meta.json file>".format(sys.argv[0])

    main(sys.argv[1])
