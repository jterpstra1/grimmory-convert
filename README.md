# grimmory-convert

Converts books in a [Grimmory](https://grimmory.org) library to extra formats with Calibre's
`ebook-convert`, and saves the result next to the original:

```
Author/Title/Title.epub   ->   Author/Title/Title.azw3
```

Grimmory's library watcher sees the new file and attaches it to the existing book as an extra
format. Grimmory itself is not changed.

## How it works

- Walks the library and, for every book in a source format (default `epub`), creates each target
  format (default `azw3`) that is missing in that folder. Existing files are never overwritten.
- Converts in a scratch dir, copies the result into the library as `*.grimmory-convert.part`
  (an extension Grimmory ignores) and renames it into place, so Grimmory never sees half a file.
- Failed conversions are written to `/config/failed.json` and skipped on later runs. Remove an
  entry to retry it.
- Folders with an `.ignore` file are skipped, like Grimmory does.
- Starts in **dry-run** mode: it only logs what it would create.

## Grimmory requirements

- The library must have **folder monitoring** enabled, or you trigger a library rescan yourself.
- The library's organisation mode must be **Auto detect** or **Book per folder**. In
  **Book per file** mode every file becomes its own book, so the converted file shows up as a
  duplicate.

## Settings

| Variable | Default | |
|---|---|---|
| `DRY_RUN` | `true` | `false` to actually convert |
| `TARGET_FORMATS` | `azw3` | Comma-separated, e.g. `azw3,mobi,pdf`. Stick to formats Grimmory knows: epub, pdf, mobi, azw3, fb2 |
| `SOURCE_FORMATS` | `epub` | Comma-separated, in order of preference when a book has several |
| `INTERVAL_MINUTES` | `0` | Minutes between runs; `0` runs once and exits |
| `MAX_PER_RUN` | `0` | Stop after this many conversions per run (`0` = no limit) |
| `EXTRA_ARGS` | | Extra `ebook-convert` arguments, e.g. `--output-profile kindle_pw3` |
| `CONVERT_TIMEOUT` | `600` | Seconds before one conversion is given up |
| `UMASK` | `000` | Unraid default, so files are readable/writable for the share like everything else |
| `TZ` | | Timezone for log timestamps |

Mounts: the library at `/books`, a small state dir at `/config`. The container runs as `99:100`
(Unraid's `nobody:users`) and needs no network.

## Unraid

1. In the Unraid terminal (`>_` in the web UI), download the template:
   ```bash
   wget -O /boot/config/plugins/dockerMan/templates-user/my-grimmory-convert.xml https://raw.githubusercontent.com/jterpstra1/unraid-templates/main/grimmory-convert.xml
   ```
2. In **Docker > Add Container**, pick **grimmory-convert** under *User templates*, point
   **Library** at the same share Grimmory uses
   (e.g. `/mnt/user/books/`), keep **Dry Run** `true` and **Max per run** `5`.
3. Start it and read the log. If the planned files look right, set **Dry Run** to `false` and
   start it again. Check in Grimmory that the new formats show up on the books.
4. Once happy, set **Max per run** to `0` and **Interval** to e.g. `60` to keep converting new
   books as they arrive.

## Running elsewhere

```bash
docker run --rm -v /path/to/books:/books -v ./config:/config \
  -e DRY_RUN=false -e TARGET_FORMATS=azw3 ghcr.io/jterpstra1/grimmory-convert
```

## Development

```bash
python3 -m unittest -v test_convert
```

The tests use a fake converter. With Calibre installed locally you can run `convert.py` directly
against a test folder: `LIBRARY_DIR=./books STATE_DIR=./state DRY_RUN=false python3 convert.py`.
