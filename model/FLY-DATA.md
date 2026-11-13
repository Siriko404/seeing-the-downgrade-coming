# Data and licences for the fruit fly models

The fly models (`src/tcf_credit/fly.py`, `src/tcf_credit/brain.py`) need the wiring diagram (connectome) of a fruit
fly's brain. This package does **not** contain that data. The code downloads two public files the first time you use
a fly model, and checks each against a pinned SHA-256 hash (a fingerprint; a changed or damaged file is refused).

## What is downloaded

| File | From | Size | What it holds |
|---|---|---|---|
| `Connectivity_783.parquet` | `https://raw.githubusercontent.com/philshiu/Drosophila_brain_model/main/Connectivity_783.parquet` | 100,804,642 bytes (about 101 MB) | Every connection between neurons of the FlyWire brain, version 783 (about 15 million), with a signed whole-number connection strength (column `Excitatory x Connectivity`; positive = excites, negative = inhibits), as prepared by Shiu et al. 2024 |
| `Supplemental_file1_neuron_annotations.tsv` | `https://raw.githubusercontent.com/flyconnectome/flywire_annotations/main/supplemental_files/Supplemental_file1_neuron_annotations.tsv` | 31,720,298 bytes (about 32 MB) | What each neuron is (cell class, cell type, ...), from Schlegel et al. 2024 and later updates |

Total: about 132.5 MB (126 MiB). The model uses the cell classes `ALPN` (input neurons) and `Kenyon_Cell`.

SHA-256 of the files (also in `fly.py`):

- `Connectivity_783.parquet`: `efeb23fb99098e9c390f6869969b2a121a2ee92c833cfc45ecb2c1d8e1af0347`
- `Supplemental_file1_neuron_annotations.tsv`: `b214970b55d2fbe0853bba536fdcb9e28730f4eb7ab06f600491df795da683cd`

## Where the files are stored (the cache)

By default in the folder `.cache/tcf_credit/fly` inside your home folder. That is outside the repository, so git
never sees it. To keep the cache elsewhere, for example inside the package, set `TCF_FLY_DIR` before you start Python:

    export TCF_FLY_DIR=/full/path/to/the/repository/model/.fly_cache

Use the full path, not a relative one: notebooks run in `model/notebooks`, and a relative path would make a second
cache there. If you put the cache inside the repository, add `model/.fly_cache/` to your `.gitignore` so the 132 MB
never end up in a commit. Delete the
folder at any time; the next run downloads the files again.

## Licences (read from the two repositories on 2026-11-12)

**Drosophila_brain_model (Shiu et al.)**: the repository has a `LICENSE` file: the MIT licence, "Copyright (c) 2023
Philip Shiu and Nico Spiller". It allows use, copying, modification and redistribution, as long as the copyright and
licence notice stay with the copies. The repository's README does not add a separate licence or citation rule for the
connectivity file. It says the repository accompanies the paper (see below).

**flywire_annotations (Schlegel et al.)**: the repository has **no licence file**, and GitHub shows none. Without a
licence, the authors keep all rights, so nobody is told in writing that the file may be copied and passed on. The
README does ask for citations (below). It states that the annotations were first described in Schlegel et al.
(2024) and invites contributions; it says nothing about redistribution.

**Can the files be redistributed? Not by this package.** The first file is under the MIT licence, which would allow
it, but it is a data table prepared from FlyWire's public release, and the repository does not say under which terms
FlyWire's own data may be passed on (we did not look beyond the two repositories). The second file has no licence at
all. So the data are not copied into this package, and the safe rule for you is the same: download from the sources
above, do not re-upload the files. The two repositories are public; only the first states a licence.

## How to cite

If you use the fly models, cite the sources of the data and of the signed wiring:

- Shiu, P. K., Sterne, G. R., et al. (2024). A Drosophila computational brain model reveals sensorimotor processing.
  *Nature* 634, 210-219. doi:10.1038/s41586-024-07763-9. (First posted as a preprint, bioRxiv 2023.05.02.539144,
  which is the version the repository's README links.)
- Schlegel, P., et al. (2024). Whole-brain annotation and multi-connectome cell typing of Drosophila. *Nature*.
  doi:10.1038/s41586-024-07686-5.
- Dorkenwald, S., et al. (2024). Neuronal wiring diagram of an adult brain. *Nature*. doi:10.1038/s41586-024-07558-y.
  This is the FlyWire connectome itself. The annotations README asks for it in every version of its citation rule,
  so cite it.

The annotation file that the code downloads today carries the changes of repository version 3.2.0. For that
version the README asks you to cite, "when using annotations from this repository", also:

- Berg, S., et al. (2026). Sexual dimorphism in the complete Drosophila male central nervous system connectome. *Cell*
  189(18), 5504-5526. doi:10.1016/j.cell.2026.08.015.
- Tastekin, I., et al. (2026). The complete gustatory connectome of adult Drosophila reveals how taste guides
  feeding, foraging, and social behavior. *Cell* 189, 5527-5551. doi:10.1016/j.cell.2026.08.016.
- Matsliah, A., et al. (2024). Neuronal parts list and wiring diagram for a visual system. *Nature*.
  doi:10.1038/s41586-024-07981-1.

The model only reads the cell class of two kinds of neurons (`ALPN`, `Kenyon_Cell`), but citing all of them follows
the repository's own request.

## One thing that can break later

Both URLs point to the `main` branch, which the authors can change. The annotation repository says its annotations
"have been updated since the initial FlyWire preprint". If a file changes, the hash check
refuses it with the message "the download does not have the pinned hash". That is intended: the results of this
package must come from the files with the hashes above. If it happens, do not weaken the check. Look for the release
tag of the repository that matches the hashes, or re-run with a new hash and say so in your results.
