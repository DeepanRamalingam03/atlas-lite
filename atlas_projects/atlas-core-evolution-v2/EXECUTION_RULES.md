# Atlas Core Evolution V2 Execution Rules

1. Execute exactly one roadmap task at a time.
2. Never begin a dependent task before its dependency is completed.
3. Treat the current Git-tracked repository as authoritative.
4. Existing files must be inspected before modification.
5. Existing files may only receive minimal targeted edits.
6. Never replace or simplify a whole existing production module.
7. Touch only the task's explicit `allowed_files`.
8. Enforce `max_files_changed` and `max_new_files`.
9. Do not edit `.env`, `.atlas_data`, credentials, secrets, locks,
   staging directories, virtual environments, or generated files.
10. Do not combine multiple roadmap tasks into one AI response.
11. Run every validation command declared by the current task.
12. Manager review must reject unrelated changes or architectural drift.
13. Each completed subtask must produce one isolated Git commit.
14. Push only after validation and manager approval.
15. Preserve runtime, Discord, alerting, usage, retry, recovery,
    project-runner, and release behavior.
