# 📦 Poetry Practicals

A minimal project to understand how to use Poetry for dependency management and running Python scripts.

---

## 📁 Project Structure

```
1_Poetry/
├── main.py
├── pyproject.toml
├── poetry.lock
```

---

## 🧾 main.py

```python
import requests
print("Hello Poetry!!")
```

---

## 🚀 Setup Instructions

### 1. Install Poetry (if not installed)

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

### 2. Navigate to project

```bash
cd 1_Poetry
```

### 3. Install dependencies

```bash
poetry install
```

### 4. Add a dependency

```bash
poetry add requests
```

---

## ▶️ Running the Script

**Option 1: Using Poetry**

```bash
poetry run python main.py
```

**Option 2: Activate virtual environment**

```bash
poetry shell
python main.py
```

---

## 🔍 Notes

| File | Purpose |
|------|---------|
| `pyproject.toml` | Manages dependencies and project config |
| `poetry.lock` | Locks exact versions |

> Poetry automatically creates and manages a virtual environment.

---

## ✅ Output

```
Hello Poetry!!
```