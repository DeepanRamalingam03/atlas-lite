from __future__ import annotations

import json

from services.worker_output_parser import WorkerOutputParser


payload = {
    "summary": "Created a sample module.",
    "files": [
        {
            "path": "sample.py",
            "content": "def hello():\n    return 'hello'\n",
        }
    ],
}

parser = WorkerOutputParser()
summary, files = parser.parse(json.dumps(payload))

assert summary == "Created a sample module."
assert len(files) == 1
assert files[0].path == "sample.py"
assert "def hello" in files[0].content

print("Worker output parser passed")
