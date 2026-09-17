# YOLO Class Review

A small internal Streamlit web app for reviewing and correcting class IDs in existing YOLO object-detection labels. It is optimized for the repeated workflow: inspect a crop, click **Correct** or select another visual class, and move immediately to the next object.

The app changes only the class token. It does not create, resize, reorder, or delete boxes. It has no authentication or automatic classification.

## Dataset ZIP

Upload one ZIP per assigned annotator. The ZIP may contain these paths directly or inside one enclosing directory:

```text
images/
  image001.jpg
labels/
  image001.txt
references/
  0.jpg
  1.jpg
  ...
  88.jpg
classes.txt       # or data.yaml
```

The class mapping must contain exactly 89 non-empty names for IDs 0 through 88. `classes.txt` uses one name per line. A YOLO-style `data.yaml` may instead provide `names` as a list or numeric-keyed dictionary. Reference image filenames must use their numeric class ID; common JPG, PNG, BMP, and WebP formats are supported.

The ZIP importer rejects path traversal, symlinks, duplicate case-insensitive destinations, excessive file counts, and excessive expanded size.

## Windows setup

Install Python 3.11 or newer, then run from this repository:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\streamlit.exe run app.py --server.address 0.0.0.0 --server.port 8501
```

Annotators on the same internal network open `http://<server-ip>:8501`.

## Linux setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

## Persistent storage

By default, imported assignments, backups, SQLite progress, and working labels are stored under `./workspace`. For deployment, point the app at a persistent, backed-up location:

Windows PowerShell:

```powershell
$env:ANNOTATE_TOOL_DATA_DIR = "D:\annotation-review-data"
.\.venv\Scripts\streamlit.exe run app.py --server.address 0.0.0.0 --server.port 8501
```

Linux:

```bash
export ANNOTATE_TOOL_DATA_DIR=/srv/annotation-review-data
.venv/bin/streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

Do not use an ephemeral directory. Schedule machine-level backups of this location; application-level atomic writes cannot protect against complete server-disk loss.

## Operating rules

- Assign each imported dataset to one annotator at a time. The MVP does not implement authentication or distributed task locking.
- Every Correct, relabel, or Skip decision is persisted immediately. Relabeling atomically replaces the working label file before progress is recorded.
- The original `labels/` tree is copied once to `backups/labels_original/` during import and is never overwritten.
- Refreshing the browser or restarting Streamlit resumes at the first unreviewed valid object.
- A displayed object is not saved until the annotator clicks Correct, Skip, or a class card.
- Malformed label files are read-only so that valid-looking lines inside a damaged file cannot be silently rewritten.

## Export and restore

Open **Export corrected labels** in the sidebar and download the ZIP. It contains:

- working `labels/`;
- `classes.txt` or `data.yaml`;
- `progress.json`;
- `problems.csv`.

Images and original backups are excluded to keep the export small. To restore an assignment after a server problem, combine an image copy with the exported labels and class metadata, then import that dataset as a new assignment. Keep the server workspace backup if original labels must also be recovered.

## Development and tests

Install development requirements and run the suite:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -v
```

Generate the demonstration ZIP:

```powershell
.\.venv\Scripts\python.exe scripts\create_sample_data.py
```

Then import `sample_data/sample_assignment.zip` in the app. It contains two valid objects plus empty, missing, and malformed-label cases.

## Troubleshooting

- **Upload rejected for size:** `.streamlit/config.toml` allows browser uploads up to 4096 MB. Increase `server.maxUploadSize` deliberately if required. The importer separately caps expanded content at 20 GB and 25,000 files.
- **Invalid archive:** confirm the ZIP contains `images/` and class metadata at its root or inside exactly one enclosing directory. Remove shortcuts, symlinks, and duplicate paths.
- **Malformed label:** inspect the file named under **Problems**. The app will not edit that label file until it is corrected and the assignment is reopened.
- **Cannot connect from another laptop:** confirm Streamlit is running with `--server.address 0.0.0.0`, Windows Firewall or the server firewall permits TCP port 8501, and the client uses the server's internal IP address.
- **Progress appears missing:** verify `ANNOTATE_TOOL_DATA_DIR` points to the same persistent directory used by the earlier run.
