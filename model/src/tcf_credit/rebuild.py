"""Pipeline runner: rebuild every output with one command, in order, from the free or the WRDS route.

Goes in:  a data folder (downloads and hand-downloaded files), an output folder, and a route: "free" or "wrds".
          Optional: --wrds-user NAME, --coverage-end YYYY-MM-DD, --from STEP and --zoo.
Comes out: the same files that the single-step commands write, in DATA_DIR and OUT_DIR (see the pipeline table in
          model/README.md). At the end it prints the pooled table in OUT_DIR/run/pooled.csv and every output path.
Data:     the free route uses public data only (FRED, the Philadelphia Fed, the SEC, Yahoo prices, the agencies'
          public rating histories and the Loughran-McDonald files). The WRDS route writes LICENSED data (CRSP and
          Compustat): keep those files on your own computer and do not share them.
Usage: python -m tcf_credit.rebuild DATA_DIR OUT_DIR --route free|wrds [--wrds-user NAME]
       [--coverage-end 2025-12-05] [--from STEP] [--zoo]

Every step is a real command (`python -m tcf_credit.<module> ...`), run with the same Python that runs this module.
A step whose output files already exist is skipped, so after a failure you can start the command again. `--from 5`
forces step 5 and every later step to run again; earlier steps are still skipped when their outputs exist. A step
that fails stops the run. Files that must be downloaded by hand (fetch_public prints the list) also stop the run.

This module only starts the other commands; each one explains its own rules and data. `fetch_wrds` asks for the WRDS
password itself and this runner never sees or stores it.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

N_STEPS = 9


class CommandFailed(Exception):
    """A step command returned a non-zero exit code."""

    def __init__(self, argv: list[str], stdout: str, stderr: str):
        self.argv, self.stdout, self.stderr = argv, stdout, stderr
        super().__init__(f"command failed: {' '.join(argv)}")


@dataclass
class Command:
    """One command line, with an optional file fed to its standard input."""
    argv: list[str]
    stdin: Path | None = None


@dataclass
class Context:
    """The folders and options shared by every step."""
    data: Path
    out: Path
    route: str
    wrds_user: str | None = None
    coverage_end: str = "2025-12-05"
    zoo: bool = False
    epoch: int = field(default_factory=lambda: 0)

    @property
    def py(self) -> str:
        return sys.executable

    def module(self, name: str) -> str:
        return f"tcf_credit.{name}"


@dataclass
class Step:
    """One numbered step: its commands, its outputs and a short explanation for a failure."""
    number: int
    title: str
    hint: str
    commands: Callable[[Context], list[Command]]
    outputs: Callable[[Context], list[Path]]
    count: Callable[[Context], tuple[Path, int] | None] | None = None
    ready: Callable[[Context], bool] | None = None
    verify: Callable[[Context], str | None] | None = None
    guard: Callable[[Context], str | None] | None = None

    def is_ready(self, ctx: Context) -> bool:
        """True when every output of this step is already there."""
        return self.ready(ctx) if self.ready else all(p.exists() for p in self.outputs(ctx))


def _csv_rows(path: Path) -> int:
    """Rows in a CSV file, not counting the header. Handles .gz too; 0 if the file cannot be read."""
    try:
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8", errors="replace", newline="") as fh:
            return max(0, sum(1 for _ in csv.reader(fh)) - 1)
    except OSError:
        return 0


def _missing_manual(ctx: Context):
    """The hand-downloaded files that are still missing (fetch_public knows the list)."""
    from tcf_credit.fetch_public import missing_manual
    return missing_manual(ctx.data)


def _free_inputs_outputs(ctx: Context) -> list[Path]:
    """Every file step 1 writes or needs before step 2 can run."""
    d = ctx.data
    return [d / "fred" / f"{s}.csv" for s in ("BAA10Y", "T10Y3M", "VIXCLS")] + \
           [d / "fred" / "realtime" / n for n in
            ("rucQvMd.xlsx", "iptMvMd.xlsx", "routput_first_second_third.xlsx")] + \
           [d / "fred" / "realtime" / n for n in ("unemployment_first_release.csv", "indpro_vintages.csv",
                                                  "indpro_first_release.csv", "gdp_growth_first_second_third.csv")] + \
           [d / "lm_headers.csv", d / "sec" / "company_tickers_exchange.json"]


def _free_inputs_ready(ctx: Context) -> bool:
    """Step 1 is ready only when its outputs and the hand-downloaded files are all there."""
    return all(p.exists() for p in _free_inputs_outputs(ctx)) and not _missing_manual(ctx)


def _manual_guard(ctx: Context) -> str | None:
    """Stop before a long download when a hand-downloaded file is still missing."""
    from tcf_credit.fetch_public import print_manual
    missing = _missing_manual(ctx)
    if not missing:
        return None
    print_manual(missing, ctx.data)
    return "manual downloads needed (see the list above); save them in the data folder, then run again"


def _free_inputs_verify(ctx: Context) -> str | None:
    """List the files that must be downloaded by hand, or the outputs that are still missing."""
    problem = _manual_guard(ctx)
    if problem:
        return problem
    absent = [p for p in _free_inputs_outputs(ctx) if not p.exists()]
    return "missing outputs: " + ", ".join(str(p) for p in absent) if absent else None


def _free_inputs_commands(ctx: Context) -> list[Command]:
    """Run the free downloads, convert the Philadelphia Fed sheets and reduce the LM header file."""
    d = ctx.data
    cmds = [Command([ctx.py, "-m", ctx.module("fetch_public"), str(d)])]
    philly = [d / "fred" / "realtime" / n for n in
              ("unemployment_first_release.csv", "indpro_vintages.csv", "indpro_first_release.csv",
               "gdp_growth_first_second_third.csv")]
    if not all(p.exists() for p in philly):
        cmds.append(Command([ctx.py, "-m", ctx.module("philly_fed"), str(d / "fred" / "realtime"),
                             str(d / "fred" / "realtime")]))
    if not (d / "lm_headers.csv").exists():
        headers = sorted((d / "lm").glob("LoughranMcDonald_10-K_HeaderData_*.csv"))
        if headers:
            cmds.append(Command([ctx.py, "-m", ctx.module("lm_headers"), str(d / "lm_headers.csv"), "2009"],
                                stdin=headers[-1]))
    sec = d / "sec"
    if not (sec / "company_tickers_exchange.json").exists():      # only the ticker list: step 3b fetches each company
        cmds.append(Command([ctx.py, "-m", ctx.module("fetch_sec_bulk"), str(sec), "--tickers-only"]))
    return cmds


def _ratings_commands(ctx: Context) -> list[Command]:
    """Read the hand-downloaded rating archives."""
    return [Command([ctx.py, "-m", ctx.module("ratings_parser"), str(ctx.data / "ratings"),
                     str(ctx.out / "ratings")])]


def _links_ready(ctx: Context) -> bool:
    """Links exist and at least one company-facts file has been written."""
    facts = ctx.data / "companyfacts"
    return (ctx.out / "links.csv").exists() and facts.is_dir() and any(facts.iterdir())


def _links_commands(ctx: Context) -> list[Command]:
    """Match rated companies to SEC numbers, then fetch their XBRL facts."""
    return [Command([ctx.py, "-m", ctx.module("link_obligors"),
                     str(ctx.out / "ratings" / "ratings_obligor_events.csv.gz"), str(ctx.data / "lm_headers.csv"),
                     str(ctx.out / "links.csv")]),
            Command([ctx.py, "-m", ctx.module("fetch_companyfacts"), str(ctx.out / "links.csv"),
                     str(ctx.data / "companyfacts"), "--us-only"])]


def _panel_commands(ctx: Context) -> list[Command]:
    """Build the panel and write the ticker lists for the price step."""
    return [Command([ctx.py, "-m", ctx.module("build_panel"),
                     str(ctx.out / "ratings" / "ratings_obligor_events.csv.gz"), str(ctx.out / "links.csv"),
                     str(ctx.data / "companyfacts"), str(ctx.out / "panel.csv"),
                     "--coverage-end", ctx.coverage_end]),
            Command([ctx.py, "-m", ctx.module("tickers"), str(ctx.out / "panel.csv"),
                     str(ctx.data / "sec" / "company_tickers_exchange.json"), str(ctx.out)])]


def _prices_free_commands(ctx: Context) -> list[Command]:
    """Download Yahoo prices, then write them in the CRSP folder layout."""
    return [Command([ctx.py, "-m", ctx.module("fetch_yahoo"), str(ctx.out / "TICKERS.txt"),
                     str(ctx.data / "yahoo")]),
            Command([ctx.py, "-m", ctx.module("yahoo_market"), str(ctx.data / "yahoo"),
                     str(ctx.out / "TICKERS.csv"), str(ctx.out / "panel.csv"), str(ctx.out / "crsp")])]


def _prices_wrds_commands(ctx: Context) -> list[Command]:
    """Pull CRSP prices from WRDS (the student types the password when the package asks)."""
    argv = [ctx.py, "-m", ctx.module("fetch_wrds"), str(ctx.out / "panel.csv"), str(ctx.out / "crsp")]
    if ctx.wrds_user:
        argv += ["--username", ctx.wrds_user]
    return [Command(argv)]


def _market_commands(ctx: Context) -> list[Command]:
    """Add return, volatility, market value and distance to default."""
    return [Command([ctx.py, "-m", ctx.module("market_features"), str(ctx.out / "panel.csv"),
                     str(ctx.out / "crsp"), str(ctx.out / "panel_market.csv")])]


def _v2_commands(ctx: Context) -> list[Command]:
    """Add ratio changes, beta, profit volatility and the first-release economy inputs."""
    return [Command([ctx.py, "-m", ctx.module("features_v2"), str(ctx.out / "panel_market.csv"),
                     str(ctx.out / "crsp"), str(ctx.data / "fred"), str(ctx.out / "panel_v2.csv")])]


def _evaluate_commands(ctx: Context) -> list[Command]:
    """Test the models year by year."""
    argv = [ctx.py, "-m", ctx.module("evaluate"), str(ctx.out / "panel_v2.csv"), str(ctx.out / "run")]
    if ctx.zoo:
        argv.append("--zoo")
    return [Command(argv)]


def _compare_commands(ctx: Context) -> list[Command]:
    """Compare the models on the same test rows."""
    return [Command([ctx.py, "-m", ctx.module("compare_models"), str(ctx.out / "run")])]


def build_steps(ctx: Context) -> list[Step]:
    """The nine steps of the pipeline, in order."""
    d, o = ctx.data, ctx.out
    crsp = o / "crsp"
    market_files = [crsp / n for n in ("crsp_links.csv", "crsp_daily.parquet", "crsp_sp500.csv", "crsp_vwretd.csv")]
    run_files = [o / "run" / n for n in ("pooled.csv", "per_year.csv", "predictions.csv", "params.json")]
    price_commands = _prices_free_commands if ctx.route == "free" else _prices_wrds_commands
    price_hint = ("check the Yahoo terms and that the ticker lists are in OUT_DIR; free prices leave out companies "
                  "that stopped trading" if ctx.route == "free" else
                  "check your WRDS account, CRSP access and the user name; this step writes licensed data")
    return [
        Step(1, "download the free inputs and prepare the economy files", "check TCF_SEC_CONTACT, the network and the "
             "hand-downloaded files printed by fetch_public", _free_inputs_commands, _free_inputs_outputs,
             ready=_free_inputs_ready, verify=_free_inputs_verify, guard=_manual_guard),
        Step(2, "read the rating histories", "check the rating ZIP files in DATA_DIR/ratings", _ratings_commands,
             lambda c: [c.out / "ratings" / "ratings_obligor_events.csv.gz", c.out / "ratings" / "MANIFEST.txt"],
             count=lambda c: (c.out / "ratings" / "ratings_obligor_events.csv.gz",
                              _csv_rows(c.out / "ratings" / "ratings_obligor_events.csv.gz"))),
        Step(3, "link companies to SEC numbers and fetch their facts",
             "check DATA_DIR/lm_headers.csv and the SEC contact", _links_commands,
             lambda c: [c.out / "links.csv", c.data / "companyfacts"], ready=_links_ready,
             count=lambda c: (c.out / "links.csv", _csv_rows(c.out / "links.csv"))),
        Step(4, "build the table and the ticker lists", "check the rating table, links and company-facts folder",
             _panel_commands, lambda c: [c.out / "panel.csv", c.out / "TICKERS.csv", c.out / "TICKERS.txt"],
             count=lambda c: (c.out / "panel.csv", _csv_rows(c.out / "panel.csv"))),
        Step(5, f"fetch the stock prices ({ctx.route} route)", price_hint, price_commands,
             lambda c: market_files, count=lambda c: (crsp / "crsp_links.csv", _csv_rows(crsp / "crsp_links.csv"))),
        Step(6, "add the market inputs", "check the price folder OUT_DIR/crsp", _market_commands,
             lambda c: [o / "panel_market.csv"],
             count=lambda c: (o / "panel_market.csv", _csv_rows(o / "panel_market.csv"))),
        Step(7, "add the changes, beta and economy inputs", "check DATA_DIR/fred and the price folder",
             _v2_commands, lambda c: [o / "panel_v2.csv"],
             count=lambda c: (o / "panel_v2.csv", _csv_rows(o / "panel_v2.csv"))),
        Step(8, "test the models year by year", "check that OUT_DIR/panel_v2.csv has enough years and both labels",
             _evaluate_commands, lambda c: run_files,
             count=lambda c: (o / "run" / "predictions.csv", _csv_rows(o / "run" / "predictions.csv"))),
        Step(9, "compare the models", "check the files in OUT_DIR/run", _compare_commands,
             lambda c: [o / "run" / "comparison.csv"],
             count=lambda c: (o / "run" / "comparison.csv", _csv_rows(o / "run" / "comparison.csv"))),
    ]


def run_command(argv: list[str], env: dict, stdin: Path | None = None) -> None:
    """Run one step command with the same Python. Raise CommandFailed on a non-zero exit code."""
    fh = open(stdin, "rb") if stdin else None
    try:
        done = subprocess.run(argv, stdin=fh, capture_output=True, text=True, env=env)
    finally:
        if fh:
            fh.close()
    if done.returncode != 0:
        raise CommandFailed(argv, done.stdout, done.stderr)


def _missing_outputs(step: Step, ctx: Context) -> str:
    """A short message naming the outputs of a step that are not there."""
    absent = [p for p in step.outputs(ctx) if not p.exists()]
    return "missing outputs: " + ", ".join(str(p) for p in absent)


def run_step(step: Step, ctx: Context, env: dict, force: bool = False) -> bool:
    """Run one step unless it is ready. Return True on success (or a skip)."""
    label = f"Step {step.number} of {N_STEPS}: {step.title}"
    if not force and step.is_ready(ctx):
        print(f"{label} ... skipped (outputs already exist)", flush=True)
        return True
    print(f"{label} ...", end="", flush=True)
    t0 = time.monotonic()
    try:
        for cmd in step.commands(ctx):
            run_command(cmd.argv, env, cmd.stdin)
            if step.guard:
                problem = step.guard(ctx)
                if problem:
                    print(" FAILED", flush=True)
                    print(f"  {problem}")
                    print(f"  check: {step.hint}")
                    return False
    except CommandFailed as e:
        print(" FAILED", flush=True)
        print(f"  command: {' '.join(e.argv)}")
        tail = (e.stderr or e.stdout or "").strip().splitlines()[-5:]
        for line in tail:
            print(f"  {line}")
        print(f"  check: {step.hint}")
        return False
    except Exception as e:                                  # a fake or a local problem; still name the step
        print(" FAILED", flush=True)
        print(f"  {type(e).__name__}: {e}")
        print(f"  check: {step.hint}")
        return False
    problem = step.verify(ctx) if step.verify else (_missing_outputs(step, ctx)
                                                    if not step.is_ready(ctx) else None)
    if problem:
        print(" FAILED", flush=True)
        print(f"  {problem}")
        print(f"  check: {step.hint}")
        return False
    seconds = time.monotonic() - t0
    rows = ""
    if step.count:
        path, n = step.count(ctx)
        if path.exists():
            rows = f", {n:,} rows"
    print(f" done{rows}, {seconds:.0f} s", flush=True)
    return True


def _print_summary(ctx: Context, steps: list[Step]) -> None:
    """Print the pooled table and the path of every output."""
    pooled = ctx.out / "run" / "pooled.csv"
    if pooled.exists():
        try:
            import pandas as pd
            table = pd.read_csv(pooled)
            show = table[table["rule"] == "calibrated_cut"] if "rule" in table else table
            print("\nPooled results (OUT_DIR/run/pooled.csv):", flush=True)
            print(show.to_string(index=False), flush=True)
        except Exception as e:
            print(f"\nCould not print {pooled}: {type(e).__name__}: {e}", flush=True)
    print("\nOutputs:", flush=True)
    seen = []
    for step in steps:
        for path in step.outputs(ctx):
            if path.exists() and path not in seen:
                seen.append(path)
                print(f"  {path}", flush=True)


def run(data: Path, out: Path, route: str = "free", wrds_user: str | None = None,
        coverage_end: str = "2025-12-05", from_step: int = N_STEPS + 1, zoo: bool = False,
        steps: list[Step] | None = None, env: dict | None = None) -> int:
    """Run the pipeline. Return 0 when every step succeeded, else 1."""
    data, out = Path(data), Path(out)
    data.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    ctx = Context(data=data, out=out, route=route, wrds_user=wrds_user, coverage_end=coverage_end, zoo=zoo)
    steps = steps if steps is not None else build_steps(ctx)
    if route == "wrds":
        print("WARNING: the WRDS route writes LICENSED CRSP and Compustat data. Keep every file it makes on your own "
              "computer and do not share it.", flush=True)
    if env is None:
        env = dict(os.environ)
        src = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = os.pathsep.join([src] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    for step in steps:
        force = step.number >= from_step
        if not run_step(step, ctx, env, force=force):
            print(f"\nStopped at step {step.number}: {step.title}.", flush=True)
            return 1
    _print_summary(ctx, steps)
    return 0


def main(argv: list[str] | None = None) -> None:
    """Read the command line and run the pipeline."""
    parser = argparse.ArgumentParser(description="Rebuild every output of the credit-downgrade model.")
    parser.add_argument("data_dir", type=Path, help="folder for downloads and hand-downloaded files")
    parser.add_argument("out_dir", type=Path, help="folder for the pipeline outputs")
    parser.add_argument("--route", choices=("free", "wrds"), default="free", help="free public data or WRDS")
    parser.add_argument("--wrds-user", default=None, help="your WRDS user name (the package asks for the password)")
    parser.add_argument("--coverage-end", default="2025-12-05", help="last day the rating data cover")
    parser.add_argument("--from", dest="from_step", type=int, default=N_STEPS + 1, choices=range(1, N_STEPS + 1),
                        metavar="STEP", help=f"redo from this step (1 to {N_STEPS})")
    parser.add_argument("--zoo", action="store_true", help="also run the extra model engines in step 8")
    args = parser.parse_args(argv)
    sys.exit(run(args.data_dir, args.out_dir, route=args.route, wrds_user=args.wrds_user,
                 coverage_end=args.coverage_end, from_step=args.from_step, zoo=args.zoo))


if __name__ == "__main__":
    main()
