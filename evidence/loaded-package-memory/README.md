# LoadedPackage Memory Benchmark

Python heap peak measurements (`tracemalloc`) comparing single-pass
`LoadedPackage` with streaming binary-media verification against `0.11.0`
(`main`, commit `58733a6`) and the initial PR #2 snapshot (`0b75b15`, before
streaming media verification).

## Scope and limitations

- **Metric:** Python heap peak reported by `tracemalloc.get_traced_memory()`.
  Native C allocations inside `libxml2` XML trees are **not** included in
  `tracemalloc`.
- **Inputs:** synthetic copies of [`corpus/base.docx`](../../corpus/base.docx)
  with an additional uncompressed (`ZIP_STORED`) binary member
  `word/media/large.bin`. Real documents with large XML parts or many
  simultaneously open trees will behave differently.
- **Environment:** CPython `3.12.8`, `macOS-27.2.1-arm64-arm-64bit`,
  `lxml 6.1.3.0`, `libxml2 2.14.6`.

## Recorded results ([`results.json`](results.json))

| Scenario | `0.11.0` (`58733a6`) | PR #2 pre-stream (`0b75b15`) | PR #2 streaming (`2bedf23`) |
| --- | ---: | ---: | ---: |
| `compare(20 MiB, 20 MiB)` | 0.14 MiB (`151,811 B`) | 0.15 MiB (`152,499 B`) | 0.15 MiB (`152,507 B`) |
| `cli check 1×20 MiB --against 20 MiB --coverage --introduced` | 40.14 MiB (`42,085,687 B`) | 42.13 MiB (`44,174,863 B`) | 2.13 MiB (`2,232,574 B`) |
| `cli check 5×10 MiB --against 10 MiB --coverage --introduced` | 20.17 MiB (`21,147,244 B`) | 32.18 MiB (`33,743,778 B`) | 2.18 MiB (`2,286,786 B`) |

## Reproduce

```bash
python research/benchmark_loaded_package_memory.py --compare main 0b75b15 2bedf23 --out evidence/loaded-package-memory/results.json
```
