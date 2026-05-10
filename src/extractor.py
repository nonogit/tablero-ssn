"""
MDB extractor: reads all SSN .mdb files from Input/ and caches to Parquet.

Backends (auto-selected by platform):
  Windows → pyodbc with Microsoft Access ODBC driver
  Linux   → mdbtools system package via subprocess (mdb-export)

On Linux, install mdbtools first:
  sudo apt-get install mdbtools
"""
import io
import platform
import subprocess
import sys
import pandas as pd
from pathlib import Path

INPUT_DIR  = Path(__file__).parent.parent / "Input"
CACHE_PATH = Path(__file__).parent.parent / "data" / "balance_cache.parquet"

_IS_WINDOWS = platform.system() == "Windows"


# ── Windows backend (pyodbc + MS Access driver) ────────────────────────────────
# pyodbc is only imported on Windows. On Linux its C extension links against
# libodbc.so.2 (unixODBC) which is typically not installed, causing an
# ImportError even before any function is called.  The guard below ensures
# the import is never attempted on non-Windows platforms.

if _IS_WINDOWS:
    try:
        import pyodbc as _pyodbc
    except ImportError as _e:
        _pyodbc = None
        print(f"[extractor] Warning: pyodbc not available ({_e})")
else:
    _pyodbc = None


def _read_mdb_windows(path: str) -> pd.DataFrame:
    if _pyodbc is None:
        raise RuntimeError(
            "pyodbc is not available. On Windows, install it with:\n"
            "  pip install pyodbc\n"
            "and ensure the Microsoft Access Database Engine is installed."
        )
    conn = _pyodbc.connect(
        f"DRIVER={{Microsoft Access Driver (*.mdb, *.accdb)}};DBQ={path};"
    )
    try:
        df = pd.read_sql("SELECT * FROM Balance", conn)
    finally:
        conn.close()
    return df


# ── Linux backend (mdbtools via subprocess) ────────────────────────────────────

_MDBTOOLS_HINT = (
    "\nTo fix this you have two options:"
    "\n"
    "\n  Option A — install mdbtools on the Raspberry Pi (reads .mdb directly):"
    "\n    sudo apt-get install mdbtools"
    "\n"
    "\n  Option B — copy the pre-built cache from Windows (recommended, no extra install):"
    "\n    scp Windows:\\path\\to\\PnL\\data\\balance_cache.parquet  pi@<pi-ip>:~/PnL/data/"
    "\n  Then move or delete the .mdb files from the Pi so they don't trigger re-extraction."
)


def _check_mdbtools() -> None:
    try:
        result = subprocess.run(
            ["mdb-export", "--help"],
            capture_output=True,
        )
    except FileNotFoundError:
        raise EnvironmentError("mdbtools (mdb-export) is not installed." + _MDBTOOLS_HINT)


def _read_mdb_linux(path: str) -> pd.DataFrame:
    try:
        result = subprocess.run(
            ["mdb-export", "-d", ",", "-q", '"', path, "Balance"],
            capture_output=True,
        )
    except FileNotFoundError:
        raise EnvironmentError("mdbtools (mdb-export) is not installed." + _MDBTOOLS_HINT)

    if result.returncode != 0:
        raise RuntimeError(
            f"mdb-export failed for {path}:\n{result.stderr.decode()}"
        )
    df = pd.read_csv(io.BytesIO(result.stdout), dtype=str)
    return df


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _fix_encoding(s):
    """Fix latin-1 / utf-8 mojibake that appears in some company names."""
    if not isinstance(s, str):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


def _read_mdb(path: str) -> pd.DataFrame:
    if _IS_WINDOWS:
        df = _read_mdb_windows(path)
    else:
        df = _read_mdb_linux(path)

    for col in ("razon_social", "desc_cuenta", "desc_subramo"):
        if col in df.columns:
            df[col] = df[col].apply(_fix_encoding)
    return df


def _cache_is_fresh() -> bool:
    if not CACHE_PATH.exists():
        return False
    cache_mtime = CACHE_PATH.stat().st_mtime
    return all(
        f.stat().st_mtime <= cache_mtime
        for f in INPUT_DIR.glob("*.mdb")
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def load_data(force: bool = False) -> pd.DataFrame:
    """
    Return the full balance DataFrame for all periods and companies.
    Uses parquet cache; re-extracts only when MDB files are newer than the cache.
    On a Raspberry Pi the parquet cache can be pre-built on Windows and copied
    over — MDB extraction will then never be triggered.
    """
    if not force and _cache_is_fresh():
        return pd.read_parquet(CACHE_PATH)

    mdb_files = sorted(INPUT_DIR.glob("*.mdb"))
    if not mdb_files:
        # No MDB files: if cache exists, serve it anyway
        if CACHE_PATH.exists():
            print("  No .mdb files found — serving existing cache.")
            return pd.read_parquet(CACHE_PATH)
        raise FileNotFoundError(
            f"No .mdb files found in {INPUT_DIR} and no cache available."
        )

    if not _IS_WINDOWS:
        _check_mdbtools()

    frames = []
    for f in mdb_files:
        print(f"  Reading {f.name} …")
        frames.append(_read_mdb(str(f)))

    df = pd.concat(frames, ignore_index=True)
    df["importe"] = pd.to_numeric(df["importe"], errors="coerce").fillna(0.0)
    df["nivel"]   = pd.to_numeric(df["nivel"],   errors="coerce").fillna(0).astype(int)
    df["quarter"] = df["periodo"].str.replace(r"-(\d)$", r"-Q\1", regex=True)

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE_PATH, index=False)
    print(f"  Cached to {CACHE_PATH}")
    return df


def company_list(df: pd.DataFrame) -> pd.DataFrame:
    """Unique companies sorted by name."""
    return (
        df[["cod_cia", "razon_social"]]
        .drop_duplicates()
        .sort_values("razon_social")
        .reset_index(drop=True)
    )


def period_list(df: pd.DataFrame) -> list[str]:
    """Sorted list of quarter labels."""
    return sorted(df["quarter"].unique().tolist())


if __name__ == "__main__":
    print(f"Platform: {platform.system()} — using {'pyodbc' if _IS_WINDOWS else 'mdbtools'} backend")
    print("Extracting all MDB files …")
    df = load_data(force=True)
    print(f"Done. Shape: {df.shape}")
    print(f"Periods: {period_list(df)}")
    print(f"Companies: {len(company_list(df))}")
