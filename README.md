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
  format (default `azw3`) that is missing in that folder.
- **Keeps converted files in sync.** When the source changes after a conversion (for example
  Grimmory writing edited metadata or a new cover into the EPUB), the converted file is made
  again on the next run. This only works if Grimmory's *Write metadata to file* setting is on
  for EPUB; otherwise edits stay in Grimmory's database and neither file changes.
- Only replaces files it created itself. A `Title.azw3` you put there yourself is never touched.
  Converted files that Grimmory moves or renames are still recognised.
- Converts in a scratch dir, copies the result into the library as `*.grimmory-convert.part`
  (an extension Grimmory ignores) and renames it into place, so Grimmory never sees half a file.
- Keeps its bookkeeping in `/config/state.json`: which files it created, from which version of
  the source, and which conversions failed. A failed conversion is retried only once the source
  changes, or when you remove its entry from `failed`.
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

Mounts: the library at `/books`, a small state dir at `/config`, and optionally Calibre plugins
at `/plugins`. The container runs as `99:100` (Unraid's `nobody:users`) and needs no network.

## Calibre plugins

Any Calibre plugin that works with `ebook-convert` can be used: plugins that add an output
format, or *File type* plugins that process a book before it is converted.

1. Put the plugin's `.zip` (the same file you would load in Calibre via *Preferences > Plugins >
   Load plugin from file*) in the folder mounted at `/plugins`.
2. If the plugin needs settings, configure it in a desktop Calibre once, then copy its settings
   file from Calibre's config folder (*Preferences > Miscellaneous > Open calibre configuration
   directory*, then `plugins/<Plugin Name>.json`) next to the zip.
3. Restart the container. The log shows `Installed Calibre plugin …` for each zip.

Plugins are installed into a fresh Calibre config on every start, so the folder is the complete
list: delete a zip and that plugin is gone after the next restart. When the contents of the
folder change, conversions that failed before are retried once, since a plugin may fix them.

Plugins run inside the container with access to your library, so only add ones you trust, and
you are responsible for what they do to your books. Grimmory only picks up formats it knows
(epub, pdf, mobi, azw3, fb2); a plugin output format like `kepub` is written but ignored by it.

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
